from sys import argv
import json
import cirq
import cirq.contrib.qasm_import
from cirq.circuits import InsertStrategy

DEFAULT_QUBITS_PER_NODE = 2
VERBOSE = True

def dict_append(d, key, append_value):
    if key not in d:
        d[key] = []
    d[key].append(append_value)


def commutes(op, left_op, right_op):
    l_control, l_targ = left_op 
    r_control, r_targ = right_op 

    check = 0
    # TODO make check more precise
    if l_control not in op and l_targ not in op:
        check += 1

    if r_control not in op and r_targ not in op:
        check += 2

    return check
 
 
def move_gate_by(layer_idx, gate, circ, delta=-1):
    move_gate_to(layer_idx, gate, circ, layer_idx+delta)

def move_gate_to(layer_idx, gate, circ, new_layer):
    circ.batch_remove([(layer_idx, gate)])
    circ.insert(gate, new_layer, strategy=InsertStrategy.Inline)




# subroutine for aggregating blocks
def merge(q1, left_pair, right_pair, circ):
    temp_circ = circ.copy()

    # check commutation rules and in-between gates to see if blocks can merge
    q2_l, is_ctrl_l, layer_l, _ = left_pair
    q2_r, is_ctrl_r, layer_r, _ = right_pair


    left_op = (q1, q2_l) if is_ctrl_l else (q2_l, q1)
    right_op = (q1, q2_r) if is_ctrl_r else (q2_r, q1)
    for layer_idx in range(layer_l + 1, layer_r):
        for curr_op in circ[layer_idx]:
            commute_check = commutes(curr_op, left_op, right_op)
            
            if commute_check == 0:
                return False, left_block, circ # merge failed
            if commute_check == 1 or commute_check == 3:
                move_gate_by(layer_idx, curr_op, temp_circ)
            if commute_check == 2:
                move_gate_by(layer_idx, curr_op, temp_circ, delta=1)

    return True, left_block + right_block, temp_circ

def aggregate(in_circ, node_map, node_array=None):

    # identify qubit-node pair with most remote gates
    rem_pairs = dict()
    qubit_ops = dict() # not used much, mostly debugging

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

    # KEY: (q,node)
    # VALUE: [block_1 ... block_n] where each block_i is a list of operations [(q1, q2)_1 ... (q1, q2)_m] 
    pair_to_merged = dict() 
    visted_ops = set() # all op that have been added to the above dict
    out_circ = in_circ.copy()
    
    for q1, node in pair_queue:
        ## PREPROCESSING (find communication blocks -- consecutive CNOTs)
        pairs = rem_pairs[(q1, node)]
        visited_pairs = set() # pairs that have been added to a block
        comm_blocks = []
        for idx in range(len(pairs)):
            if idx in visited_pairs:
                continue

            q2, q1_ctrl, layer_idx, _ = pairs[idx]

            ### ignore ops that are already part of a diff (q, node) pair
            curr_op = (q1, q2, layer_idx) if q1_ctrl else (q2, q1, layer_idx)
            if curr_op in visited_ops:
                continue
            visited_ops.add(curr_op)
            ######

            
            visited_pairs.add(idx)
            comm_blocks.append([idx])

            for idx_next in range(idx+1, len(pairs)):
                _, _, layer_idx_next, _ = pairs[idx_next]
                if layer_idx_next > layer_idx + 1:
                    break

                # consecutive pairs
                visited_pairs.add(idx_next)
                comm_blocks[-1].append(idx_next)
                layer_idx += 1 # curr idx becomes next

        if VERBOSE:
            print(f'{(q1,node)} consecutive blocks: {comm_blocks}') # debug

        
        ## LINEAR MERGE
        visited_blocks = set()
        merged_blocks = [] # blocks that have completed merging
        for idx, block in enumerate(comm_blocks):
            if idx in visited_blocks:
                continue
            visited_blocks.add(idx)

            block_modified = block
            for idx_next in range(idx+1, len(comm_blocks)):
                left_pair = pairs[block[-1]]
                right_pair = pairs[comm_blocks[idx_next][0]]

                did_merge, block_modified, out_circ = merge(q1, left_pair, right_pair, out_circ)
                if not did_merge:
                    merged_blocks.append(block_modified)
                    break
                visited_blocks.add(idx_next)

        pair_to_merged[(q1, node)] = merged_blocks

    return pair_to_merged, rem_pairs, out_circ

def is_bidirectional(q1, block):
    assert len(block) > 0
    if len(block) == 1:
        return False

    direction = block[0][1]
    ctrls = []

    birectional = False
    for q2, q1_ctrl, _, _ in block:
        ctrls.append(q1 if q1_ctrl else q2)

        # if at least one direction is diff from the first, bi=True
        if q1_ctrl != direction:
            bidirectional = True

    return bidirectional, ctrls


commuting_singles = {cirq.Z, cirq.Rz, cirq.S, cirq.I}
def single_X_interferes(op, ctrl):
    q = op.qubits[0]
    if q != ctrl:
        return False, False

    return op.gate not in commuting_singles, True

# checks if there exits single qubit gates that cannot commute
def check_unidirectional(l_layer, r_layer, ctrls, circ):
    commuting_gates = [] # [(op, layer_idx)_k]

    for layer_idx in range(l_layer+1, r_layer):
        for op in circ[layer_idx]:
            if len(op.qubits) > 1:
                continue

            noncommuting, should_move = unzip([single_X_interferes(op, ctrl) for ctrl in ctrls[:recent_block_index+1]])
            if any(noncommuting):
                return True

            if any(should_move):
                commuting_gates.append((op, layer_idx))

    # move single qubit gates that target the ctrl back
    for op, layer_idx in commuting_gates:
        move_gate_to(layer_idx, op, circ, l_layer)
    return False


def assign(in_circ, pair_to_blocks, pair_to_ops, node_array=None):
    out_circ = in_circ.copy()
    tp_assign = dict() # KEY: ((q, node), block_index), VALUE: True or False
    for pair, blocks in pair_to_blocks.items():
        for idx, block in enumerate(blocks):
            block_details = [pair_to_ops[pair][p] for p in block]
            q1, node = pair
            bi, ctrls = is_bidirectional(q1, block_details)

            if bi:
                tp_assign[(pair, idx)] = True # TP-COM
            else:
                # check for single qubit gates on ctrls in the block 
                tp_assign[(pair, idx)] = check_unidrectional(block_details[0].layer, block_details[-1].layer, ctrls, out_circ)

    return tp_assign, out_circ

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


    pair_to_blocks, pair_to_ops, agg_circuit = aggregate(input_circuit, node_map)
    print(agg_circuit)

    assignments, assigned_circuit = assign(agg_circuit, node_map, pair_to_blocks, pair_to_ops)
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
