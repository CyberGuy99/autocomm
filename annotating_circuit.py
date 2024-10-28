import simpy

# 定义延迟时间
SINGLE_QUBIT_GATE_DELAY = 1
TWO_QUBIT_GATE_DELAY = 10
ENTANGLEMENT_DELAY = 100

class QuantumGate:
    def __init__(self, gate_type, qubits, qpus_involved, circuit, initiating_qpu):
        self.gate_type = gate_type
        self.qubits = qubits
        self.qpus_involved = qpus_involved  # 涉及的 QPU 列表
        self.circuit = circuit
        self.initiating_qpu = initiating_qpu  # 发起执行该门的 QPU

    def is_remote(self):
        return len(self.qpus_involved) > 1

class Circuit:
    def __init__(self, env, circuit_id, gates, qpus, scheduler):
        self.env = env
        self.circuit_id = circuit_id
        self.gates = gates
        self.qpus = qpus
        self.scheduler = scheduler
        self.completion_event = env.event()
        self.remaining_gates = len(gates)
        self.logical_to_physical = {}  # 逻辑比特到物理比特的映射
        self.action = env.process(self.run())

    def run(self):
        # 输出逻辑比特到物理比特的映射
        print(f"时间 {self.env.now}: 电路 {self.circuit_id} 的逻辑比特到物理比特映射：")
        for logical_qubit, (qpu_id, physical_qubit) in self.logical_to_physical.items():
            print(f"  逻辑比特 {logical_qubit} -> QPU {qpu_id}, 物理比特 {physical_qubit}")
        # 将门映射到对应的QPU
        for gate in self.gates:
            qpus_involved = set()
            for logical_qubit in gate['qubits']:
                qpu_id, _ = self.logical_to_physical[logical_qubit]
                qpus_involved.add(qpu_id)
            qpus_involved = list(qpus_involved)
            initiating_qpu_id = qpus_involved[0]
            initiating_qpu = self.qpus[initiating_qpu_id]
            gate_obj = QuantumGate(gate['type'], gate['qubits'], qpus_involved, self, initiating_qpu)
            # 仅将门放入发起 QPU 的队列
            initiating_qpu.gate_queue.put(gate_obj)
        # 等待电路执行完成
        yield self.completion_event
        # 释放物理比特资源
        self.scheduler.release_qubits(self)
        self.scheduler.active_circuits.remove(self)
        # 激活scheduler 执行下一个电路
        yield self.env.process(self.scheduler.run())
        print(f"时间 {self.env.now}: 调度器检测到电路 {self.circuit_id} 执行完成, 激活下一个电路")

    def gate_done(self):
        self.remaining_gates -= 1
        if self.remaining_gates == 0:
            self.completion_event.succeed()

class QPU:
    def __init__(self, env, qpu_id, num_computing_qubits, num_communication_qubits):
        self.env = env
        self.qpu_id = qpu_id
        self.num_computing_qubits = num_computing_qubits
        self.num_communication_qubits = num_communication_qubits
        self.gate_queue = simpy.Store(env)
        # 初始化计算比特，每个比特用一个资源表示
        self.qubits = {i: simpy.Resource(env, capacity=1) for i in range(num_computing_qubits)}
        # 初始化通信比特，每个比特用一个资源表示
        self.communication_qubits = {i: simpy.Resource(env, capacity=1) for i in range(num_communication_qubits)}
        # 物理比特的占用情况
        self.qubit_allocation = {}
        self.action = env.process(self.run())

    def run(self):
        while True:
            gate = yield self.gate_queue.get()
            # 仅处理自己发起的门
            if self != gate.initiating_qpu:
                continue
            # 启动一个新的进程来执行该门，而不等待其完成
            self.env.process(self.execute_gate(gate))

    def execute_gate(self, gate):
        if len(gate.qubits) == 1:
            # 单比特门
            yield self.env.process(self.execute_single_qubit_gate(gate))
        elif len(gate.qubits) == 2:
            if gate.is_remote():
                # 远程双比特门
                yield self.env.process(self.execute_remote_gate(gate))
            else:
                # 本地双比特门
                yield self.env.process(self.execute_local_two_qubit_gate(gate))
        # 通知电路该门已完成
        gate.circuit.gate_done()

    def execute_single_qubit_gate(self, gate):
        logical_qubit = gate.qubits[0]
        circuit = gate.circuit
        qpu_id, physical_qubit = circuit.logical_to_physical[logical_qubit]
        assert qpu_id == self.qpu_id, "单比特门的 QPU 与逻辑比特所在的 QPU 不一致"
        with self.qubits[physical_qubit].request() as req:
            yield req
            print(f"时间 {self.env.now}: QPU {self.qpu_id} 开始在电路 {circuit.circuit_id} 的逻辑比特 {logical_qubit} (物理比特 {physical_qubit}) 上执行单比特门 {gate.gate_type}")
            yield self.env.timeout(SINGLE_QUBIT_GATE_DELAY)
            print(f"时间 {self.env.now}: QPU {self.qpu_id} 完成单比特门 {gate.gate_type} (电路 {circuit.circuit_id}, 逻辑比特 {logical_qubit})")

    def execute_local_two_qubit_gate(self, gate):
        circuit = gate.circuit
        logical_qubit1, logical_qubit2 = gate.qubits
        qpu_id1, physical_qubit1 = circuit.logical_to_physical[logical_qubit1]
        qpu_id2, physical_qubit2 = circuit.logical_to_physical[logical_qubit2]
        assert qpu_id1 == self.qpu_id == qpu_id2, "本地双比特门的 QPU 与逻辑比特所在的 QPU 不一致"
        with self.qubits[physical_qubit1].request() as req1, self.qubits[physical_qubit2].request() as req2:
            yield req1 & req2
            print(f"时间 {self.env.now}: QPU {self.qpu_id} 开始在电路 {circuit.circuit_id} 的逻辑比特 {logical_qubit1}, {logical_qubit2} 上执行本地双比特门 {gate.gate_type}")
            yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
            print(f"时间 {self.env.now}: QPU {self.qpu_id} 完成本地双比特门 {gate.gate_type} (电路 {circuit.circuit_id})")

    def execute_remote_gate(self, gate):
        circuit = gate.circuit
        # 获取本地涉及的逻辑比特和对应的物理比特
        local_logical_qubits = [q for q in gate.qubits if circuit.logical_to_physical[q][0] == self.qpu_id]
        local_physical_qubits = [circuit.logical_to_physical[q][1] for q in local_logical_qubits]
        # 请求本地物理比特资源
        data_qubit_requests = [self.qubits[qubit_id].request() for qubit_id in local_physical_qubits]
        yield simpy.events.AllOf(self.env, data_qubit_requests)
        # 请求通信比特资源
        comm_qubit_id, comm_qubit_request = yield self.env.process(self.get_available_comm_qubit())
        # 参与的 QPU 列表
        other_qpus = [circuit.qpus[qpu_id] for qpu_id in gate.qpus_involved if qpu_id != self.qpu_id]
        # 用于同步的事件列表
        entanglement_events = []
        for qpu in other_qpus:
            entanglement_event = self.env.event()
            self.env.process(qpu.participate_in_remote_gate(self, gate, entanglement_event))
            entanglement_events.append(entanglement_event)
        # 等待纠缠建立延迟
        yield self.env.timeout(ENTANGLEMENT_DELAY)
        # 等待所有 QPU 准备就绪
        yield simpy.events.AllOf(self.env, entanglement_events)
        # 执行远程门
        print(f"时间 {self.env.now}: QPU {self.qpu_id} 在电路 {circuit.circuit_id} 上执行远程门 {gate.gate_type}，涉及逻辑比特 {local_logical_qubits}")
        yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
        print(f"时间 {self.env.now}: QPU {self.qpu_id} 完成远程门 {gate.gate_type}")
        # 释放资源
        for req in data_qubit_requests:
            req.resource.release(req)
        self.release_comm_qubit(comm_qubit_request)

    def participate_in_remote_gate(self, initiating_qpu, gate, entanglement_event):
        circuit = gate.circuit
        # 获取本地涉及的逻辑比特和对应的物理比特
        local_logical_qubits = [q for q in gate.qubits if circuit.logical_to_physical[q][0] == self.qpu_id]
        local_physical_qubits = [circuit.logical_to_physical[q][1] for q in local_logical_qubits]
        # 请求本地物理比特资源
        data_qubit_requests = [self.qubits[qubit_id].request() for qubit_id in local_physical_qubits]
        yield simpy.events.AllOf(self.env, data_qubit_requests)
        # 请求通信比特资源
        comm_qubit_id, comm_qubit_request = yield self.env.process(self.get_available_comm_qubit())
        # 等待纠缠建立延迟
        yield self.env.timeout(ENTANGLEMENT_DELAY)
        print(f"时间 {self.env.now}: QPU {self.qpu_id} 已准备好与 QPU {initiating_qpu.qpu_id} 执行远程门 {gate.gate_type} (电路 {circuit.circuit_id})")
        # 通知发起的 QPU 已准备就绪
        entanglement_event.succeed()
        # 等待远程门执行完成
        yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
        print(f"时间 {self.env.now}: QPU {self.qpu_id} 完成远程门 {gate.gate_type}")
        # 释放资源
        for req in data_qubit_requests:
            req.resource.release(req)
        self.release_comm_qubit(comm_qubit_request)

    def get_available_comm_qubit(self):
        # 请求一个可用的通信比特
        requests = []
        for qubit_id, resource in self.communication_qubits.items():
            request = resource.request()
            requests.append((qubit_id, request))
            if len(resource.queue) == 0 and len(resource.users) == 0:
                # 立即可用
                yield request
                return qubit_id, request
        # 如果没有立即可用的通信比特，则等待任意一个
        request_dict = {request: qubit_id for qubit_id, request in requests}
        result = yield simpy.events.AnyOf(self.env, [req for _, req in requests])
        request = next(iter(result.events))
        qubit_id = request_dict[request]
        return qubit_id, request

    def release_comm_qubit(self, request):
        # 释放通信比特资源
        request.resource.release(request)

    # def release_qubit(self, qubit_id):
    #     # 释放物理比特资源
    #     self.qubits[qubit_id].release()

class Scheduler:
    def __init__(self, env, qpus, circuits):
        self.env = env
        self.qpus = qpus
        self.circuits = circuits  # 待调度的电路列表
        self.action = env.process(self.run())
        self.active_circuits = []
        self.qubit_allocation = {}  # {QPU_ID: set(物理比特ID)}
        for qpu_id in qpus:
            self.qubit_allocation[qpu_id] = set()
        self.max_executed_circuit_id = 0

    def run(self):
        circuits_to_run = []
        # circuit_id = 0
        # while self.circuits:
        tt_circuits_num = len(self.circuits)
        # while circuit_id < tt_circuits_num:
        if self.circuits:
            # 直到没有电路可调度
            while self.circuits: # 尝试执行尽可能多的电路，直到资源不足
                circuit_gates = self.circuits[0]

                # print(f'circuit width: {max(qubit for gate in circuit_gates for qubit in gate["qubits"]) + 1}, available qubits: {all_available_physical_qubits_num}, all qubits: {all_available_physical_qubits}')
                if not self.has_enough_qubits(circuit_gates):
                    # yield self.env.timeout(1)  # 等待一段时间后重试
                    print(f"时间 {self.env.now}: 调度器等待物理比特资源 for circuit {self.max_executed_circuit_id}")
                    break
                # circuit = Circuit(self.env, len(self.active_circuits) + len(circuits_to_run), circuit_gates, self.qpus, self)
                circuit = Circuit(self.env, self.max_executed_circuit_id, circuit_gates, self.qpus, self)
                allocation_successful = self.allocate_qubits(circuit)
                print(f"时间 {self.env.now}: 电路 {self.max_executed_circuit_id} 分配物理比特 {'成功' if allocation_successful else '失败'}")
                # print(f"时间 {self.env.now}: 当前物理比特占用情况 {self.qubit_allocation}")
                if allocation_successful:
                    self.circuits.pop(0)
                    circuits_to_run.append(circuit)
                    print(f"时间 {self.env.now}: 电路 {self.max_executed_circuit_id} 开始执行")
                    # yield circuit.completion_event
                    circuits_to_run.append(circuit)
                    self.max_executed_circuit_id += 1
                else:
                    print(f"时间 {self.env.now}: 电路 {self.max_executed_circuit_id} 等待物理比特资源")
                    break
            # 同时执行多个电路，无需等待
            for circuit in circuits_to_run:
                self.active_circuits.append(circuit)
            # break
        yield self.env.timeout(0)  # 等待一段时间后重试
        print(f"时间 {self.env.now}: 调度器完成一次调度")

    def has_enough_qubits(self, circuit_gates):
        all_available_physical_qubits = {}
        for qpu_id, qpu in self.qpus.items():
            all_available_physical_qubits[qpu_id] = set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id]

        all_available_physical_qubits_num = sum(len(qubits) for qubits in all_available_physical_qubits.values())
        return max(qubit for gate in circuit_gates for qubit in gate['qubits']) + 1  <= all_available_physical_qubits_num

        # 检查电路是否有足够的物理比特可用
        

    def circuit_satisfied(self, circuit):
        # 检查电路是否有足够的物理比特可用
        num_logical_qubits = max(qubit for gate in circuit.gates for qubit in gate['qubits']) + 1
        all_avaliable_physical_qubits = set()
        for qpu_id, qpu in self.qpus.items():
            all_avaliable_physical_qubits.update(set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id])
        if len(all_avaliable_physical_qubits) < num_logical_qubits:
            return False
        

        return True

    def decided_to_run(self, circuit):
        return True
       
    def allocate_qubits(self, circuit):
        # 统计电路中涉及的逻辑比特数
        num_logical_qubits = max(qubit for gate in circuit.gates for qubit in gate['qubits']) + 1
        # 为电路分配物理比特
        circuit.logical_to_physical = {}
        decided_to_run = self.decided_to_run(circuit)

        if not decided_to_run:
            return False
        
        for logical_qubit in range(num_logical_qubits):
            # 查找可用的QPU和物理比特
            allocated = False
            for qpu_id, qpu in self.qpus.items():
                available_qubits = set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id]
                if available_qubits:
                    physical_qubit = available_qubits.pop()
                    circuit.logical_to_physical[logical_qubit] = (qpu_id, physical_qubit)
                    self.qubit_allocation[qpu_id].add(physical_qubit)
                    # print(f'circuit {circuit.circuit_id} allocate qubit {physical_qubit} on QPU {qpu_id}, crt_qubits_allocation: {self.qubit_allocation}')
                    allocated = True
                    break
                
        # for logical_qubit in range(num_logical_qubits):
        #     # 查找可用的QPU和物理比特
        #     allocated = False
        #     for qpu_id, qpu in self.qpus.items():
        #         available_qubits = set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id]
        #         if available_qubits:
        #             physical_qubit = available_qubits.pop()
        #             circuit.logical_to_physical[logical_qubit] = (qpu_id, physical_qubit)
        #             self.qubit_allocation[qpu_id].add(physical_qubit)
        #             allocated = True
        #             # with qpu.qubits[physical_qubit].request() as req:
        #             #     yield req
        #             break
            # if not allocated:
        # else:
        #     # 没有足够的物理比特可用，电路需要等待
        #     print(f"时间 {self.env.now}: 电路 {circuit.circuit_id} 等待物理比特资源")
        #     yield self.env.timeout(1)  # 等待一段时间后重试
        #     yield self.env.process(self.allocate_qubits(circuit))
        #     # return
        # return satisfied

        return True

    def release_qubits(self, circuit):
        # 释放电路占用的物理比特
        print(f"时间 {self.env.now}: 电路 {circuit.circuit_id} 释放物理比特资源11111")
        for qpu_id, physical_qubit in circuit.logical_to_physical.values():
            self.qubit_allocation[qpu_id].remove(physical_qubit)
            # self.qpus[qpu_id].release_qubit(physical_qubit)


def simulate(quantum_circuits, qpu_qubit_counts):
    env = simpy.Environment()
    # 创建 QPU
    qpus = {}
    for qpu_id, qubit_counts in qpu_qubit_counts.items():
        num_computing_qubits = qubit_counts['computing']
        num_communication_qubits = qubit_counts['communication']
        qpus[qpu_id] = QPU(env, qpu_id, num_computing_qubits, num_communication_qubits)

    # 创建调度器
    scheduler = Scheduler(env, qpus, quantum_circuits)

    env.run()

# 示例用法
if __name__ == '__main__':
    # 定义量子电路
    quantum_circuits = [
        [
            {'type': 'H', 'qubits': [0]},
            {'type': 'CNOT', 'qubits': [0, 1]},
            {'type': 'X', 'qubits': [1]},
            {'type': 'CZ', 'qubits': [1, 2]},
        ],
        [
            {'type': 'Z', 'qubits': [0]},
            {'type': 'CNOT1', 'qubits': [0, 1]},
            {'type': 'REMOTE_CZ', 'qubits': [0, 2]},
        ],
        [
            {'type': 'Z', 'qubits': [0]},
            {'type': 'CNOT1', 'qubits': [0, 1]},
            {'type': 'REMOTE_CZ', 'qubits': [0, 4]},
        ],
    ]

    # 每个 QPU 拥有的计算比特和通信比特数量
    qpu_qubit_counts = {
        'QPU1': {'computing': 4, 'communication': 1},  # QPU1 有 4 个计算比特，2 个通信比特
        'QPU2': {'computing': 2, 'communication': 1},  # QPU2 有 3 个计算比特，1 个通信比特
    }

    simulate(quantum_circuits, qpu_qubit_counts)

