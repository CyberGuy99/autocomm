import cirq

def make_qft(qubits):
    """Generator for the QFT on a list of qubits."""
    qreg = list(qubits)
    while len(qreg) > 0:
        q_head = qreg.pop(0)
        yield cirq.H(q_head)
        for i, qubit in enumerate(qreg):
            yield (cirq.CZ ** (1 / 2 ** (i + 1)))(qubit, q_head)


def gen_qft_circuit(num_qubits):
    qubits = cirq.LineQubit.range(num_qubits)
    return cirq.Circuit(make_qft(qubits))
