import simpy

# Define delay times
SINGLE_QUBIT_GATE_DELAY = 1
TWO_QUBIT_GATE_DELAY = 10
ENTANGLEMENT_DELAY = 100

class QuantumGate:
    def __init__(self, gate_type, qubits, qpus_involved, circuit, initiating_qpu):
        self.gate_type = gate_type
        self.qubits = qubits
        self.qpus_involved = qpus_involved  # List of involved QPUs
        self.circuit = circuit
        self.initiating_qpu = initiating_qpu  # QPU that initiates the execution of the gate

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
        self.logical_to_physical = {}  # Mapping from logical qubits to physical qubits
        self.action = env.process(self.run())

    def run(self):
        # Output the logical-to-physical qubit mapping
        print(f"Time {self.env.now}: Circuit {self.circuit_id}'s logical-to-physical qubit mapping:")
        for logical_qubit, (qpu_id, physical_qubit) in self.logical_to_physical.items():
            print(f"  Logical qubit {logical_qubit} -> QPU {qpu_id}, physical qubit {physical_qubit}")
        # Map gates to the corresponding QPU
        for gate in self.gates:
            qpus_involved = set()
            for logical_qubit in gate['qubits']:
                qpu_id, _ = self.logical_to_physical[logical_qubit]
                qpus_involved.add(qpu_id)
            qpus_involved = list(qpus_involved)
            initiating_qpu_id = qpus_involved[0]
            initiating_qpu = self.qpus[initiating_qpu_id]
            gate_obj = QuantumGate(gate['type'], gate['qubits'], qpus_involved, self, initiating_qpu)
            # Only place the gate in the initiating QPU's queue
            initiating_qpu.gate_queue.put(gate_obj)
        # Wait for the circuit to complete execution
        yield self.completion_event
        # Release physical qubit resources
        self.scheduler.release_qubits(self)
        self.scheduler.active_circuits.remove(self)
        # Activate scheduler to execute the next circuit
        yield self.env.process(self.scheduler.run())
        print(f"Time {self.env.now}: Scheduler detected that circuit {self.circuit_id} has completed, activating the next circuit")

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
        # Initialize computing qubits, each represented by a resource
        self.qubits = {i: simpy.Resource(env, capacity=1) for i in range(num_computing_qubits)}
        # Initialize communication qubits, each represented by a resource
        self.communication_qubits = {i: simpy.Resource(env, capacity=1) for i in range(num_communication_qubits)}
        # Allocation status of physical qubits
        self.qubit_allocation = {}
        self.action = env.process(self.run())

    def run(self):
        while True:
            gate = yield self.gate_queue.get()
            # Only process gates initiated by this QPU
            if self != gate.initiating_qpu:
                continue
            # Start a new process to execute the gate without waiting for its completion
            self.env.process(self.execute_gate(gate))

    def execute_gate(self, gate):
        if len(gate.qubits) == 1:
            # Single-qubit gate
            yield self.env.process(self.execute_single_qubit_gate(gate))
        elif len(gate.qubits) == 2:
            if gate.is_remote():
                # Remote two-qubit gate
                yield self.env.process(self.execute_remote_gate(gate))
            else:
                # Local two-qubit gate
                yield self.env.process(self.execute_local_two_qubit_gate(gate))
        # Notify the circuit that the gate is done
        gate.circuit.gate_done()

    def execute_single_qubit_gate(self, gate):
        logical_qubit = gate.qubits[0]
        circuit = gate.circuit
        qpu_id, physical_qubit = circuit.logical_to_physical[logical_qubit]
        assert qpu_id == self.qpu_id, "QPU for the single-qubit gate does not match the QPU where the logical qubit is located"
        with self.qubits[physical_qubit].request() as req:
            yield req
            print(f"Time {self.env.now}: QPU {self.qpu_id} starts executing single-qubit gate {gate.gate_type} on logical qubit {logical_qubit} (physical qubit {physical_qubit}) in circuit {circuit.circuit_id}")
            yield self.env.timeout(SINGLE_QUBIT_GATE_DELAY)
            print(f"Time {self.env.now}: QPU {self.qpu_id} completes single-qubit gate {gate.gate_type} (circuit {circuit.circuit_id}, logical qubit {logical_qubit})")

    def execute_local_two_qubit_gate(self, gate):
        circuit = gate.circuit
        logical_qubit1, logical_qubit2 = gate.qubits
        qpu_id1, physical_qubit1 = circuit.logical_to_physical[logical_qubit1]
        qpu_id2, physical_qubit2 = circuit.logical_to_physical[logical_qubit2]
        assert qpu_id1 == self.qpu_id == qpu_id2, "QPU for the local two-qubit gate does not match the QPU where the logical qubits are located"
        with self.qubits[physical_qubit1].request() as req1, self.qubits[physical_qubit2].request() as req2:
            yield req1 & req2
            print(f"Time {self.env.now}: QPU {self.qpu_id} starts executing local two-qubit gate {gate.gate_type} on logical qubits {logical_qubit1}, {logical_qubit2} in circuit {circuit.circuit_id}")
            yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
            print(f"Time {self.env.now}: QPU {self.qpu_id} completes local two-qubit gate {gate.gate_type} (circuit {circuit.circuit_id})")

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
        # List of participating QPUs
        other_qpus = [circuit.qpus[qpu_id] for qpu_id in gate.qpus_involved if qpu_id != self.qpu_id]
        # List of synchronization events
        entanglement_events = []
        for qpu in other_qpus:
            entanglement_event = self.env.event()
            self.env.process(qpu.participate_in_remote_gate(self, gate, entanglement_event))
            entanglement_events.append(entanglement_event)
        # Wait for entanglement delay
        yield self.env.timeout(ENTANGLEMENT_DELAY)
        # Wait for all QPUs to be ready
        yield simpy.events.AllOf(self.env, entanglement_events)
        # Execute the remote gate
        print(f"Time {self.env.now}: QPU {self.qpu_id} executes remote gate {gate.gate_type} in circuit {circuit.circuit_id}, involving logical qubits {local_logical_qubits}")
        yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
        print(f"Time {self.env.now}: QPU {self.qpu_id} completes remote gate {gate.gate_type}")
        # Release resources
        for req in data_qubit_requests:
            req.resource.release(req)
        self.release_comm_qubit(comm_qubit_request)

    def participate_in_remote_gate(self, initiating_qpu, gate, entanglement_event):
        circuit = gate.circuit
        # Get local logical qubits and corresponding physical qubits
        local_logical_qubits = [q for q in gate.qubits if circuit.logical_to_physical[q][0] == self.qpu_id]
        local_physical_qubits = [circuit.logical_to_physical[q][1] for q in local_logical_qubits]
        # Request resources for local physical qubits
        data_qubit_requests = [self.qubits[qubit_id].request() for qubit_id in local_physical_qubits]
        yield simpy.events.AllOf(self.env, data_qubit_requests)
        # Request communication qubit resources
        comm_qubit_id, comm_qubit_request = yield self.env.process(self.get_available_comm_qubit())
        # Wait for entanglement delay
        yield self.env.timeout(ENTANGLEMENT_DELAY)
        print(f"Time {self.env.now}: QPU {self.qpu_id} is ready to execute remote gate {gate.gate_type} with QPU {initiating_qpu.qpu_id} (circuit {circuit.circuit_id})")
        # Notify the initiating QPU that it is ready
        entanglement_event.succeed()
        # Wait for the remote gate to complete
        yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
        print(f"Time {self.env.now}: QPU {self.qpu_id} completes remote gate {gate.gate_type}")
        # Release resources
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
        self.max_executed_circuit_id = 0

    def run(self):
        circuits_to_run = []
        total_circuits_num = len(self.circuits)
        if self.circuits:
            # Keep trying to schedule circuits as long as resources are available
            while self.circuits:
                circuit_gates = self.circuits[0]

                if not self.has_enough_qubits(circuit_gates):
                    print(f"Time {self.env.now}: Scheduler waiting for physical qubit resources for circuit {self.max_executed_circuit_id}")
                    break

                circuit = Circuit(self.env, self.max_executed_circuit_id, circuit_gates, self.qpus, self)
                allocation_successful = self.allocate_qubits(circuit)
                print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} allocated physical qubits {'successfully' if allocation_successful else 'unsuccessfully'}")

                if allocation_successful:
                    self.circuits.pop(0)
                    circuits_to_run.append(circuit)
                    print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} starts execution")
                    circuits_to_run.append(circuit)
                    self.max_executed_circuit_id += 1
                else:
                    print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} waiting for physical qubit resources")
                    break
            # Execute multiple circuits simultaneously
            for circuit in circuits_to_run:
                self.active_circuits.append(circuit)

        yield self.env.timeout(0)
        print(f"Time {self.env.now}: Scheduler completed a scheduling round")

    def has_enough_qubits(self, circuit_gates):
        all_available_physical_qubits = {}
        for qpu_id, qpu in self.qpus.items():
            all_available_physical_qubits[qpu_id] = set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id]

        total_available_qubits_num = sum(len(qubits) for qubits in all_available_physical_qubits.values())
        return max(qubit for gate in circuit_gates for qubit in gate['qubits']) + 1 <= total_available_qubits_num

    def allocate_qubits(self, circuit):
        # Count the number of logical qubits involved in the circuit
        num_logical_qubits = max(qubit for gate in circuit.gates for qubit in gate['qubits']) + 1
        # Allocate physical qubits for the circuit
        circuit.logical_to_physical = {}
        
        for logical_qubit in range(num_logical_qubits):
            allocated = False
            for qpu_id, qpu in self.qpus.items():
                available_qubits = set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id]
                if available_qubits:
                    physical_qubit = available_qubits.pop()
                    circuit.logical_to_physical[logical_qubit] = (qpu_id, physical_qubit)
                    self.qubit_allocation[qpu_id].add(physical_qubit)
                    allocated = True
                    break

        return True

    def release_qubits(self, circuit):
        # Release the physical qubits occupied by the circuit
        print(f"Time {self.env.now}: Circuit {circuit.circuit_id} releasing physical qubit resources")
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

    # Number of computing and communication qubits for each QPU
    qpu_qubit_counts = {
        'QPU1': {'computing': 4, 'communication': 1},  # QPU1 has 4 computing qubits, 2 communication qubits
        'QPU2': {'computing': 2, 'communication': 1},  # QPU2 has 3 computing qubits, 1 communication qubit
    }

    simulate(quantum_circuits, qpu_qubit_counts)
