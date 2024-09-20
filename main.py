from sys import argv
import json
import cirq
import cirq.contrib.qasm_import

DEFAULT_QUBITS_PER_NODE = 2
VERBOSE = True

def dict_append(d, key, append_value):
    if key not in d:
        d[key] = []
    d[key].append(append_value)
 

# subroutine for aggregating blocks
def merge(left_block, right_block, pairs, qubit_ops):
    left_pair = pairs[left_block[-1]]
    right_pair = pairs[right_block[0]]

    # check commutation rules and in-between gates to see if blocks can merge
    q2_l, is_ctrl_l, _, op_idx_l = left_pair
    q2_r, is_ctrl_r, _, op_idx_r = right_pair

    for op_idx in range(op_idx_l + 1, op_idx_r):
        curr_op = qubit_ops[op_idx]


    return True, left_block + right_block

def aggregate(in_circ, node_map, node_array=None):

    # identify qubit-node pair with most remote gates
    rem_pairs = dict()
    qubit_ops = dict()

    for layer_idx, layer in enumerate(in_circ):
        for op in layer:
            # skip if operation is single-qubit (assumming no X-qubit gates for X>2)
            if len(op.qubits) != 2:
                continue
            
            ctrl, targ = op.qubits
            targ_node = node_map(targ)
            ctrl_node = node_map(ctrl)

            # skip if controlled operation is local
            if ctrl_node == targ_node:
                continue

            dict_append(qubit_ops, ctrl, (targ, True))
            dict_append(qubit_ops, targ, (ctrl, False))

            # appending useful information
            dict_append(rem_pairs, (ctrl, targ_node), (targ,True,layer_idx, len(qubit_ops[ctrl])-1) )
            dict_append(rem_pairs, (targ, ctrl_node), (ctrl,False,layer_idx, len(qubit_ops[targ])-1) )

   
    # max_pair_len = -1
    # max_pair = None
    # for pair, num_pairs in rem_pairs.items():
    #     if max_pair_len < len(num_pairs):
    #         max_pair_len = len(num_pairs)
    #         max_pair = pair
    pair_queue = sorted(rem_pairs, key = lambda p: len(rem_pairs[p]), reverse=True)
    if len(pair_queue) == 0:
        return in_circ.copy()

    max_pair_len = len(rem_pairs[pair_queue[0]])
    if VERBOSE:
        print(f'qubit node {pair_queue[0]} has most interaction: {max_pair_len} remote gates')

    ## ITERATIVE REFINEMENT
    for q1, node in pair_queue:
        ## PREPROCESSING (find communication blocks)
        pairs = rem_pairs[(q1, node)]
        visited_pairs = set() # pairs that have been added to a block
        comm_blocks = []
        for idx in range(len(pairs)):
            if idx in visited_pairs:
                continue

            _, _, layer_idx, _ = pairs[idx]
            visited_pairs.add(idx)
            comm_blocks.append([idx])

            for idx_next in range(idx+1, len(pairs)):
                _, _, layer_idx_next, _ = pairs[idx_next]
                if layer_idx_next > layer_idx + 1:
                    break

                # consecutive pairs
                visited_pairs.add(idx_next)
                comm_blocks[-1].append(idx_next)
                layer_idx += 1 # next idx becomes current

        if VERBOSE:
            print(f'{(q1,node)} consecutive blocks: {comm_blocks}') # debug

        
        ## LINEAR MERGE
        visited_blocks = set()
        for idx, block in enumerate(comm_blocks):
            if idx in visited_blocks:
                continue
                
            for idx_next in range(idx+1, len(comm_blocks)):
                did_merge, blocks = merge(block, comm_blocks[idx_next], pairs, qubit_ops)
                if not did_merge:
                    break
                visited_blocks.add(idx_next)






                
            
                
    return in_circ.copy()


def assign(in_circ, node_map, node_array=None):
    return in_circ.copy()

def schedule(in_circ, node_map, node_array=None):
    return in_circ.copy()

def map_to_nodes(num_nodes, in_circ):
    qubit_to_node = dict()
    num_qubits = len(in_circ.all_qubits())
    node_array = []
    if num_nodes == 0:
        num_nodes = min(DEFAULT_QUBITS_PER_NODE * num_qubits, num_qubits)

    qubits_per_node = num_qubits // num_nodes
    for idx, q in enumerate(in_circ.all_qubits()):
        qubit_to_node[q] = idx // qubits_per_node
        node_array.append(idx // qubits_per_node)

    return qubit_to_node, node_array




def main(raw_input, in_type, num_nodes=0):
    if in_type > 3 or in_type < 0:
        print("Invalid input: input type should be integer between [0,3]")
        return None

    if in_type < 3:
        with open(raw_input) as f:
            input = f.read()
    else:
        input = raw_input
    
    input_circuit = import_circuit(input, in_type)
    node_map, node_arr = map_to_nodes(num_nodes, input_circuit)


    agg_circuit = aggregate(input_circuit, node_map)
    print(agg_circuit)

    assigned_circuit = assign(agg_circuit, node_map)
    print(assigned_circuit)

    scheduled_circuit = schedule(assigned_circuit, node_map)
    print(scheduled_circuit)

    return scheduled_circuit



# 0: json string input in cirq format (generated by cirq)
# 1: json string input in quirk format (generated by quirk)
# 2: qasm string input (experimental)
# 3: url input, quirk
def import_circuit(input, in_type=0):
    if in_type == 0:
        return cirq.read_json(json_text=input)
    if in_type == 1:
        return cirq.quirk_json_to_circuit(json.loads(input))
    if in_type == 2:
        return cirq.contrib.qasm_import(input)
    if in_type == 3:
        return cirq.quirk_url_to_circuit(input)



if __name__ == '__main__':
    if len(argv) < 3:
        print("Invalid input: expected 2 arguments")
        exit()

    raw_input = argv[1]
    in_type = int(argv[2])
    num_nodes = int(argv[3]) if len(argv) > 3 else 0

    main(raw_input, in_type, num_nodes)