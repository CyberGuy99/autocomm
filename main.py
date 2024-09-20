from sys import argv
import json
import cirq
import cirq.contrib.qasm_import
from cirq.circuits import InsertStrategy

from data_structures import Block, Pair

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
def merge(left_pair, right_pair, circ):
    temp_circ = circ.copy()

    # check commutation rules and in-between gates to see if blocks can merge

    left_op = left_pair.get_op_tuple() 
    right_op = right_pair.get_op_tuple()
    for layer_idx in range(left_pair.layer_idx + 1, right_pair.layer_idx):
        for curr_op in circ[layer_idx]:
            commute_check = commutes(curr_op, left_op, right_op)
            
            if commute_check == 0:
                return False, circ # merge failed
            if commute_check == 1 or commute_check == 3:
                move_gate_by(layer_idx, curr_op, temp_circ)
            if commute_check == 2:
                move_gate_by(layer_idx, curr_op, temp_circ, delta=1)

    return True, temp_circ

def aggregate(in_circ, node_map, node_array=None):

    # identify qubit-node pair with most remote gates
    rem_pairs = dict()
    qubit_ops = dict() # unused, debugging

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
            ctrl_pair = Pair(ctrl, targ_node, ctrl_node, targ, True, layer_idx)
            targ_pair = Pair(targ, ctrl_node, targ_node, ctrl, False, layer_idx)
            dict_append(rem_pairs, (ctrl, targ_node), ctrl_pair)
            dict_append(rem_pairs, (targ, ctrl_node), targ_pair)

   
    pair_queue = sorted(rem_pairs, key = lambda p: len(rem_pairs[p]), reverse=True)
    if len(pair_queue) == 0:
        return in_circ.copy(), None, None

    max_pair_len = len(rem_pairs[pair_queue[0]])
    if VERBOSE:
        print(f'qubit node {pair_queue[0]} has most interaction: {max_pair_len} remote gates')

    ## ITERATIVE REFINEMENT

    # KEY: (q,node)
    # VALUE: [block_1 ... block_n] where each block_i is a list of operations [(q1, q2)_1 ... (q1, q2)_m] 
    pair_to_merged = dict() 
    visited_ops = set() # all op that have been added to the above dict
    out_circ = in_circ.copy()
    
    for q1, node in pair_queue:
        ## PREPROCESSING (find communication blocks -- consecutive CNOTs)
        pairs = rem_pairs[(q1, node)]
        visited_pairs = set() # pairs that have been added to a block
        comm_blocks = []
        for idx in range(len(pairs)):
            if idx in visited_pairs:
                continue

            curr_op = pairs[idx].get_op_tuple()

            ### ignore ops that are already part of a diff (q, node) pair
            if curr_op in visited_ops:
                continue
            visited_ops.add(curr_op)
            ######

            
            visited_pairs.add(idx)
            comm_blocks.append([idx])

            for idx_next in range(idx+1, len(pairs)):
                if pairs[idx_next].layer_idx > layer_idx + 1:
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
                left_block = block[-1]
                right_block = comm_blocks[idx_next][0]

                did_merge, out_circ = merge(pairs[left_block], pairs[right_block], out_circ)
                if not did_merge:
                    merged_blocks.append(block_modified)
                    break
                block_modified = left_block + right_block
                visited_blocks.add(idx_next)

        pair_to_merged[(q1, node)] = merged_blocks

    return pair_to_merged, rem_pairs, out_circ

def is_bidirectional(block):
    assert len(block) > 0
    if len(block) == 1:
        return False

    ctrls = [pair.get_ctrl_q() for pair in block]
    directions = [pair.is_ctrl for pair in block]
    bidirectional = not all(directions) and any(directions) # not all True and one is True
    return bidirectional, ctrls


commuting_singles = {cirq.Z, cirq.Rz, cirq.S, cirq.I}
def single_X_interferes(op, ctrl):
    q = op.qubits[0]
    if q != ctrl:
        return False, False

    return op.gate not in commuting_singles, True

# checks if there exits single qubit gates that cannot commute
def check_unidirectional(block_idxs, ctrls, circ):
    commuting_gates = [] # [(op, layer_idx)_k]

    l_layer = block_idxs[0]
    r_layer = block_idxs[-1]
    recent_block_idx = 0
    for layer_idx in range(l_layer+1, r_layer):
        # if we have moved past the next block, update the recent index
        if layer_idx > block_idxs[recent_block_idx + 1]:
            recent_block_idx += 1

        for op in circ[layer_idx]:
            if len(op.qubits) > 1:
                continue

            noncommuting, should_move = zip(*[single_X_interferes(op, ctrl) for ctrl in ctrls[:recent_block_idx+1]])
            if any(noncommuting):
                return True

            if any(should_move):
                commuting_gates.append((op, layer_idx))

    # move single qubit gates that target the ctrl back
    for op, layer_idx in commuting_gates:
        move_gate_to(layer_idx, op, circ, l_layer)
    return False


def assign(in_circ, pair_to_blocks, pair_to_ops):
    out_circ = in_circ.copy()
    tp_assign = dict() # KEY: ((q, node), block_index), VALUE: True or False
    for pair, blocks in pair_to_blocks.items():
        # block is a collection of op indices, typically consecutive
        for idx, block in enumerate(blocks):
            block_details = [pair_to_ops[pair][p] for p in block] # redundant indexing, it is given that they are consecutive
            bi, ctrls = is_bidirectional(block_details)

            if bi:
                tp_assign[(pair, idx)] = True # TP-COM
            else:
                # check for single qubit gates on ctrls in the block 
                block_idxs = [b.layer_idx for b in block_details]
                tp_assign[(pair, idx)] = check_unidirectional(block_idxs, ctrls, out_circ)

    return tp_assign, out_circ

NUM_COMM_NODES = 2
def must_serialize_cat(first_block, second_block, node_map, usage):
    (q1_1, node2_1), _ = first_block[0]
    (q1_2, node2_2), _ = second_block[0]
    assert not (q1_1 == q1_2 and node2_1 == node2_2)

    if q1_1 == q1_2:
        # must be on different nodes, same qubit cannot be sent to two diff nodes concurrently
        return True
    
    node1_1 = node_map[q1_1]
    node1_2 = node_map[q1_2]
    if node1_1 != node1_2 and node2_1 != node2_2:
        # totally independent
        return False

    # must count 
    return usage[node1_1] < NUM_COMM_NODES and usage[node1_2] < NUM_COMM_NODES \
            and usage[node2_1] < NUM_COMM_NODES and usage[node2_2] < NUM_COMM_NODES


def must_serialize_tp(first_block, second_block, node_map, usage):
    return must_serialize_cat(first_block, second_block, node_map, usage)

def greedy_schedule(blocks, node_map, is_tp):
    concurrents = [] # array of arrays, each subarray has consecutive block indices
    visited_blocks = set()
    for idx, block_info in enumerate(blocks):
        if idx in visited_blocks:
            continue
        concurrents.append[ [idx] ]
        visited_blocks.add(idx)

        usage = dict()
        q1_1, node2_1 = block_info[0] # first pair in the block is fine, they all have same (q, node)
        usage[node_map[q1_1]] = 1
        usage[node2_1] = 1

        for idx_next in range(idx+1, blocks):
            next_block_info = blocks[idx_next]
            if (is_tp and must_serialize_tp(block_info, next_block_info, node_map, usage)) \
                    or (not is_tp and must_serialize_cat(block_info, next_block_info, node_map, usage)):
                break


            q2_1, node2_2 = next_block_info[0]
            if node_map[q2_1] not in usage:
                node_map[q2_1] = 0
            usage[node_map[q2_1]] += 1

            if node_map[node2_2] not in usage:
                node_map[node2_2] = 0
            usage[node2_2] += 1

            concurrents[-1].append(idx_next)
            visited_blocks.add(idx_next)

    return concurrents




def schedule(in_circ, tp_pair_blocks, cat_pair_blocks, node_map):
    out_circ = in_circ.copy() # circuit should stay the same, only changing metadata (comm schedule)

    concurrent_cats = greedy_schedule(cat_pair_blocks, node_map, is_tp=False) 
    concurrent_tps = greedy_schedule(tp_pair_blocks, node_map, is_tp=True) 

    return out_circ, (concurrent_tps, concurrent_cats)

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
    if not agg_circuit:
        print('Invalid Input Circuit')
        print(input_circuit)
        return

    print(agg_circuit)

    assignments, assigned_circuit = assign(agg_circuit, pair_to_blocks, pair_to_ops)
    print(assigned_circuit)

    # indexing into the list of block *indices* for each pair, using idx
    # using pair_to_ops to get the block details from each (pair, block_idx)
    tp_blocks = [(pair, pair_to_ops[pair][pair_to_blocks[pair][idx]]) for (pair, idx), is_tp in assignments.items() if is_tp]
    cat_blocks = [(pair, pair_to_ops[pair][pair_to_blocks[pair][idx]]) for (pair, idx), is_tp in assignments.items() if not is_tp]

    scheduled_circuit, concurrent_tps, concurrent_cats = schedule(assigned_circuit, tp_blocks, cat_blocks)
    print(scheduled_circuit)
    print(concurrent_tps)
    print(concurrent_cats)

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
