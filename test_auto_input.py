from autocomm_v2.experiment import CircuitGen
from annotating_circuit import get_circuit_input as gci

from qubit_partition import pymetis_partition as partition
from annotating_circuit import simulate

BV = CircuitGen.BV
QFT = CircuitGen.QFT
RCA = CircuitGen.RCA


b_gl,b_m = BV(100, 10)
r_gl,r_m = RCA(100, 10)
q_gl,q_m = QFT(100, 10)


circuits = []
inputs = [(10, b_gl), (10, q_gl), (10, r_gl)]

qpu_qubit_counts = {
        'QPU1': {'computing': 50, 'communication': 1},  # QPU1 has 4 computing qubits, 2 communication qubits
        'QPU2': {'computing': 50, 'communication': 1},  # QPU2 has 3 computing qubits, 1 communication qubit
    }

ss0 = {0: 0, 1: 0, 8: 0, 9: 0, 11: 0, 19: 0, 25: 0, 29: 0, 30: 0, 31: 0, 2: 1, 3: 1, 4: 1, 6: 1, 10: 1, 52: 1, 62: 1, 64: 1, 75: 1, 96: 1, 22: 2, 33: 2, 35: 2, 36: 2, 37: 2, 38: 2, 39: 2, 40: 2, 41: 2, 51: 2, 53: 3, 54: 3, 55: 3, 56: 3, 57: 3, 61: 3, 67: 3, 68: 3, 70: 3, 73: 3, 7: 4, 47: 4, 71: 4, 74: 4, 76: 4, 79: 4, 82: 4, 86: 4, 89: 4, 91: 4, 12: 5, 46: 5, 59: 5, 60: 5, 65: 5, 66: 5, 84: 5, 90: 5, 95: 5, 98: 5, 13: 6, 14: 6, 15: 6, 16: 6, 17: 6, 18: 6, 20: 6, 21: 6, 26: 6, 34: 6, 50: 7, 58: 7, 78: 7, 85: 7, 87: 7, 88: 7, 92: 7, 93: 7, 94: 7, 97: 7, 5: 8, 32: 8, 42: 8, 44: 8, 48: 8, 63: 8, 77: 8, 80: 8, 81: 8, 83: 8, 23: 9, 24: 9, 27: 9, 28: 9, 43: 9, 45: 9, 49: 9, 69: 9, 72: 9, 99: 9}
ss1 = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 9: 0, 68: 0, 8: 1, 10: 1, 12: 1, 13: 1, 15: 1, 17: 1, 20: 1, 67: 1, 70: 1, 98: 1, 11: 2, 14: 2, 16: 2, 18: 2, 19: 2, 21: 2, 22: 2, 23: 2, 66: 2, 96: 2, 25: 3, 26: 3, 34: 3, 35: 3, 38: 3, 39: 3, 40: 3, 41: 3, 64: 3, 65: 3, 24: 4, 58: 4, 59: 4, 60: 4, 61: 4, 63: 4, 71: 4, 73: 4, 94: 4, 95: 4, 29: 5, 30: 5, 31: 5, 32: 5, 33: 5, 36: 5, 37: 5, 43: 5, 48: 5, 54: 5, 27: 6, 46: 6, 52: 6, 55: 6, 56: 6, 57: 6, 62: 6, 82: 6, 89: 6, 90: 6, 28: 7, 44: 7, 45: 7, 47: 7, 49: 7, 50: 7, 51: 7, 53: 7, 78: 7, 79: 7, 42: 8, 69: 8, 72: 8, 74: 8, 75: 8, 76: 8, 83: 8, 84: 8, 87: 8, 97: 8, 77: 9, 80: 9, 81: 9, 85: 9, 86: 9, 88: 9, 91: 9, 92: 9, 93: 9, 99: 9}
ss2 = {79: 0, 80: 0, 81: 0, 82: 0, 83: 0, 84: 0, 85: 0, 86: 0, 87: 0, 88: 0, 89: 1, 90: 1, 91: 1, 92: 1, 93: 1, 94: 1, 95: 1, 96: 1, 97: 1, 98: 1, 50: 2, 51: 2, 52: 2, 53: 2, 54: 2, 55: 2, 56: 2, 57: 2, 58: 2, 59: 2, 70: 3, 71: 3, 72: 3, 73: 3, 74: 3, 75: 3, 76: 3, 77: 3, 78: 3, 60: 4, 61: 4, 62: 4, 63: 4, 64: 4, 65: 4, 66: 4, 67: 4, 68: 4, 69: 4, 0: 5, 1: 5, 2: 5, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5, 8: 5, 9: 5, 10: 6, 11: 6, 12: 6, 13: 6, 14: 6, 15: 6, 16: 6, 17: 6, 18: 6, 19: 6, 20: 7, 21: 7, 22: 7, 23: 7, 24: 7, 25: 7, 26: 7, 27: 7, 28: 7, 29: 7, 40: 8, 41: 8, 42: 8, 43: 8, 44: 8, 45: 8, 46: 8, 47: 8, 48: 8, 49: 8, 30: 9, 31: 9, 32: 9, 33: 9, 34: 9, 35: 9, 36: 9, 37: 9, 38: 9, 39: 9}
ss = [ss0, ss1, ss2]

def individual_test(index, do_part=False):
    num_nodes, gate_list = inputs[index]
    mapping = ss[index]
    if do_part:
        mapping = partition(num_nodes, gate_list=gate_list)

    circuits = [gci(gate_list, mapping)]
    simulate(circuits, qpu_qubit_counts)

for num_nodes, gate_list in inputs[:]:
    qubit_to_node, _ = partition(num_nodes=num_nodes, gate_list=gate_list)
    circuits.append(gci(gate_list, qubit_to_node))
simulate(circuits, qpu_qubit_counts)

'''
mem = [7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 4, 4, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
print(len(mem))

import numpy as np
node_to_qubits = {}
for node in range(10):
        q_idxs = np.argwhere(np.array(mem) == node).ravel()
        node_to_qubits[node] = q_idxs

print(node_to_qubits[1])
'''

#individual_test(1)
print('success')