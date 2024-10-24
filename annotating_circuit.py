import simpy

# Define delay times
SINGLE_QUBIT_GATE_DELAY = 1
TWO_QUBIT_GATE_DELAY = 10
ENTANGLEMENT_DELAY = 100

class QuantumGate:
    def __init__(self, gate_type, qubits, qpus_involved, circuit):
        self.gate_type = gate_type
        self.qubits = qubits  # List of involved logical qubits
        self.qpus_involved = qpus_involved  # List of involved QPUs
        self.circuit = circuit  # Circuit to which this gate belongs

class Circuit:
    def __init__(self, env, circuit_id, gates, qpus, scheduler):
        self.env = env
        self.circuit_id = circuit_id
        self.gates = gates
        self.qpus = qpus
        self.scheduler = scheduler
        self.completion_event = env.event()
        self.remaining_gates = len(gates)
        self.logical_to_physical = {}  # Mapping from logical qubits to physical qubits
        self.action = env.process(self.run())

    def run(self):
        # Request the required physical qubit resources
        yield self.env.process(self.scheduler.allocate_qubits(self))
        # Map gates to the corresponding QPU
        for gate in self.gates:
            qpus_involved = set()
            for logical_qubit in gate['qubits']:
                qpu_id, physical_qubit = self.logical_to_physical[logical_qubit]
                qpus_involved.add(self.qpus[qpu_id])
            gate_obj = QuantumGate(gate['type'], gate['qubits'], list(qpus_involved), self)
            for qpu in qpus_involved:
                qpu.gate_queue.put(gate_obj)
        # Wait for circuit execution to complete
        yield self.completion_event
        # Release the physical qubit resources
        self.scheduler.release_qubits(self)

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
        self.communication_channel = simpy.Store(env)
        # Initialize computing qubits, each represented by a resource
        self.qubits = {i: simpy.Resource(env, capacity=1) for i in range(num_computing_qubits)}
        # Initialize communication qubits, each represented by a resource
        self.communication_qubits = {i: simpy.Resource(env, capacity=1) for i in range(num_communication_qubits)}
        # Allocation status of physical qubits: {physical_qubit_ID: (circuit_ID, logical_qubit_ID)}
        self.qubit_allocation = {}
        self.action = env.process(self.run())

    def run(self):
        while True:
            gate = yield self.gate_queue.get()
            # Start a new process to execute the gate
            self.env.process(self.execute_gate(gate))

    def execute_gate(self, gate):
        if len(gate.qubits) == 1 and len(gate.qpus_involved) == 1:
            # Single-qubit gate
            logical_qubit = gate.qubits[0]
            circuit = gate.circuit
            qpu_id, physical_qubit = circuit.logical_to_physical[logical_qubit]
            with self.qubits[physical_qubit].request() as req:
                yield req
                print(f"Time {self.env.now}: QPU {self.qpu_id} starts executing single-qubit gate {gate.gate_type} on qubit {logical_qubit} (physical qubit {physical_qubit}) in circuit {circuit.circuit_id}")
                yield self.env.timeout(SINGLE_QUBIT_GATE_DELAY)
                print(f"Time {self.env.now}: QPU {self.qpu_id} completes single-qubit gate {gate.gate_type} on qubit {logical_qubit} in circuit {circuit.circuit_id}")
        elif len(gate.qubits) == 2 and len(gate.qpus_involved) == 1:
            # Two-qubit gate within the same QPU
            circuit = gate.circuit
            logical_qubit1, logical_qubit2 = gate.qubits
            _, physical_qubit1 = circuit.logical_to_physical[logical_qubit1]
            _, physical_qubit2 = circuit.logical_to_physical[logical_qubit2]
            with self.qubits[physical_qubit1].request() as req1, self.qubits[physical_qubit2].request() as req2:
                yield req1 & req2
                print(f"Time {self.env.now}: QPU {self.qpu_id} starts executing two-qubit gate {gate.gate_type} on qubits {logical_qubit1}, {logical_qubit2} in circuit {circuit.circuit_id}")
                yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
                print(f"Time {self.env.now}: QPU {self.qpu_id} completes two-qubit gate {gate.gate_type} in circuit {circuit.circuit_id}")
        else:
            # Remote gate across QPUs
            yield self.env.process(self.execute_remote_gate(gate))
        # Notify the circuit that the gate has been completed
        gate.circuit.gate_done()

    def execute_remote_gate(self, gate):
        circuit = gate.circuit
        # Get local logical qubits and corresponding physical qubits
        local_logical_qubits = [q for q in gate.qubits if circuit.logical_to_physical[q][0] == self.qpu_id]
        local_physical_qubits = [circuit.logical_to_physical[q][1] for q in local_logical_qubits]
        # Request resources for local physical qubits
        data_qubit_requests = [self.qubits[qubit_id].request() for qubit_id in local_physical_qubits]
        yield simpy.events.AllOf(self.env, data_qubit_requests)
        # Request communication qubit resources
        comm_qubit_id, comm_qubit_request = yield self.env.process(self.get_available_comm_qubit())
        # Establish entanglement with other QPUs
        other_qpus = [qpu for qpu in gate.qpus_involved if qpu.qpu_id != self.qpu_id]
        for qpu in other_qpus:
            # The other QPU also needs to request a communication qubit
            other_comm_qubit_id, other_comm_qubit_request = yield self.env.process(qpu.get_available_comm_qubit())
            print(f"Time {self.env.now}: QPU {self.qpu_id} using communication qubit {comm_qubit_id} is establishing entanglement with QPU {qpu.qpu_id}'s communication qubit {other_comm_qubit_id}")
            yield self.env.timeout(ENTANGLEMENT_DELAY)
            print(f"Time {self.env.now}: QPU {self.qpu_id} has established entanglement with QPU {qpu.qpu_id}")
            qpu.communication_channel.put((self.qpu_id, gate))
            # Release the other QPU's communication qubit
            qpu.release_comm_qubit(other_comm_qubit_request)
        # Wait for confirmation from other QPUs
        for _ in other_qpus:
            sender_id, received_gate = yield self.communication_channel.get()
            print(f"Time {self.env.now}: QPU {self.qpu_id} received confirmation from QPU {sender_id}")
        # Execute the remote gate
        print(f"Time {self.env.now}: QPU {self.qpu_id} is executing remote gate {gate.gate_type} on qubits {local_logical_qubits} in circuit {circuit.circuit_id}")
        yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
        print(f"Time {self.env.now}: QPU {self.qpu_id} completes remote gate {gate.gate_type}")
        # Release the local physical qubits and communication qubit resources
        for req in data_qubit_requests:
            req.resource.release(req)
        self.release_comm_qubit(comm_qubit_request)

    def get_available_comm_qubit(self):
        # Request an available communication qubit
        requests = []
        for qubit_id, resource in self.communication_qubits.items():
            request = resource.request()
            requests.append((qubit_id, request))
            if len(resource.queue) == 0 and len(resource.users) == 0:
                # Immediately available
                yield request
                return qubit_id, request
        # If no communication qubit is immediately available, wait for any one
        request_dict = {request: qubit_id for qubit_id, request in requests}
        result = yield simpy.events.AnyOf(self.env, [req for _, req in requests])
        request = next(iter(result.events))
        qubit_id = request_dict[request]
        return qubit_id, request

    def release_comm_qubit(self, request):
        # Release the communication qubit resource
        request.resource.release(request)

class Scheduler:
    def __init__(self, env, qpus, circuits):
        self.env = env
        self.qpus = qpus
        self.circuits = circuits  # List of circuits to be scheduled
        self.action = env.process(self.run())
        self.active_circuits = []
        self.qubit_allocation = {}  # {QPU_ID: set(physical_qubit_ID)}
        for qpu_id in qpus:
            self.qubit_allocation[qpu_id] = set()

    def run(self):
        for idx, circuit_gates in enumerate(self.circuits):
            print(f"Time {self.env.now}: Scheduler starts executing circuit {idx}")
            circuit = Circuit(self.env, idx, circuit_gates, self.qpus, self)
            self.active_circuits.append(circuit)
            # Execute multiple circuits concurrently, no need to wait
        # Wait for all circuits to complete
        for circuit in self.active_circuits:
            yield circuit.completion_event
            print(f"Time {self.env.now}: Scheduler detects that circuit {circuit.circuit_id} has completed")
        # New circuits or other logic can be added here

    def allocate_qubits(self, circuit):
        # Count the number of logical qubits involved in the circuit
        num_logical_qubits = max(qubit for gate in circuit.gates for qubit in gate['qubits']) + 1
        # Allocate physical qubits for the circuit
        circuit.logical_to_physical = {}
        for logical_qubit in range(num_logical_qubits):
            # Find available QPU and physical qubits
            allocated = False
            for qpu_id, qpu in self.qpus.items():
                available_qubits = set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id]
                if available_qubits:
                    physical_qubit = available_qubits.pop()
                    circuit.logical_to_physical[logical_qubit] = (qpu_id, physical_qubit)
                    self.qubit_allocation[qpu_id].add(physical_qubit)
                    allocated = True
                    break
            if not allocated:
                # Not enough physical qubits available, circuit needs to wait
                print(f"Time {self.env.now}: Circuit {circuit.circuit_id} is waiting for physical qubit resources")
                yield self.env.timeout(1)  # Wait for a while and retry
                yield self.env.process(self.allocate_qubits(circuit))
                return

    def release_qubits(self, circuit):
        # Release the physical qubits occupied by the circuit
        for qpu_id, physical_qubit in circuit.logical_to_physical.values():
            self.qubit_allocation[qpu_id].remove(physical_qubit)

def simulate(quantum_circuits, qpu_qubit_counts):
    env = simpy.Environment()
    # Create QPUs
    qpus = {}
    for qpu_id, qubit_counts in qpu_qubit_counts.items():
        num_computing_qubits = qubit_counts['computing']
        num_communication_qubits = qubit_counts['communication']
        qpus[qpu_id] = QPU(env, qpu_id, num_computing_qubits, num_communication_qubits)

    # Create scheduler
    scheduler = Scheduler(env, qpus, quantum_circuits)

    env.run()

# Example usage
if __name__ == '__main__':
    # Define quantum circuits
    quantum_circuits = [
        [
            {'type': 'H', 'qubits': [0]},
            {'type': 'CNOT', 'qubits': [0, 1]},
            {'type': 'X', 'qubits': [1]},
            {'type': 'CZ', 'qubits': [1, 2]},
        ],
        # [
        #     {'type': 'Z', 'qubits': [0]},
        #     {'type': 'CNOT', 'qubits': [0, 1]},
        #     {'type': 'REMOTE_CZ', 'qubits': [1, 2]},
        # ],
    ]

    # Number of computing and communication qubits on each QPU
    qpu_qubit_counts = {
        'QPU1': {'computing': 1, 'communication': 2},  # QPU1 has 1 computing qubit, 2 communication qubits
        'QPU2': {'computing': 3, 'communication': 1},  # QPU2 has 3 computing qubits, 1 communication qubit
    }

    simulate(quantum_circuits, qpu_qubit_counts)
