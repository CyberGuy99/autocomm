from sys import argv
import json
import cirq
import cirq.contrib.qasm_import
from cirq.circuits import InsertStrategy

from data_structures import Block, Pair, PairAggregationSet
from qubit_partition import pymetis_partition
from utils.util import dict_append, dict_num_add

DEFAULT_QUBITS_PER_NODE = 2
VERBOSE = True


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

def aggregate(in_circ, node_map):

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
        pairs = rem_pairs[(q1, node)] # list of Pairs.
        visited_pairs = set() # pairs that have been added to a block
        comm_blocks = [] # list of lists of pair indices. max index is len(pairs) - 1. 
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
                left_block_last_pair = block[-1] # pair index
                right_block_first_pair = comm_blocks[idx_next][0]

                did_merge, out_circ = merge(pairs[left_block_last_pair], pairs[right_block_first_pair], out_circ)
                if not did_merge:
                    merged_blocks.append(block_modified)
                    break
                block_modified = block + comm_blocks[idx_next]
                visited_blocks.add(idx_next)

        merged_blocks_with_info = [ Block([pairs[pair_idx] for pair_idx in block]) for block in merged_blocks]
        pair_to_merged[(q1, node)] = merged_blocks_with_info

    return PairAggregationSet(clustered_blocks=pair_to_merged, clustered_pairs=rem_pairs), out_circ

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


def assign(in_circ: cirq.Circuit, aggregations: PairAggregationSet):
    out_circ = in_circ.copy()
    tp_assign = dict() # KEY: ((q, node), block_index), VALUE: True or False
    for pair, blocks in aggregations.get_keyed_blocks():
        # block is a collection of op indices, typically consecutive
        for idx, block in enumerate(blocks):
            assert type(block) is Block

            bi, ctrls = is_bidirectional(block.pairs)

            if bi:
                tp_assign[(pair, idx)] = True # TP-COM
            else:
                # check for single qubit gates on ctrls in the block 
                block_idxs = [pair.layer_idx for pair in block.pairs]
                tp_assign[(pair, idx)] = check_unidirectional(block_idxs, ctrls, out_circ)

    return tp_assign, out_circ

NUM_COMM_NODES = 2
def must_serialize_cat(first_pair, second_pair, usage):
    assert not (first_pair.qubit == second_pair.qubit and first_pair.node == second_pair.node)

    if first_pair.qubit == second_pair.qubit:
        # must be on different nodes, same qubit cannot be sent to two diff nodes concurrently
        return True
    
    nodes = [first_pair.node, second_pair.node, first_pair.qubit_node, second_pair.qubit_node]
    if nodes[0] != nodes[1] and nodes[2] != nodes[3]:
        # totally independent
        return False

    # must count 
    return all([usage(node) < NUM_COMM_NODES for node in nodes])


def must_serialize_tp(first_block, second_block, usage):
    return must_serialize_cat(first_block, second_block, usage)

def greedy_schedule(blocks: list[Block], is_tp):
    concurrents = [] # array of arrays, each subarray has consecutive block indices
    visited_blocks = set()
    for idx, (_, block) in enumerate(blocks.items()):
        if idx in visited_blocks:
            continue
        concurrents.append[ [idx] ]
        visited_blocks.add(idx)

        usage = dict()
        curr_pair = block.get_pair()
        usage[curr_pair.qubit_node] = 1 # node the qubit belongs to
        usage[curr_pair.node] = 1 # main node

        for idx_next in range(idx+1, blocks):
            next_pair = blocks[idx_next].get_pair()
            if (is_tp and must_serialize_tp(curr_pair, next_pair, usage)) \
                    or (not is_tp and must_serialize_cat(curr_pair, next_pair, usage)):
                break

            curr_qubit_node = next_pair.qubit_node
            curr_main_node = next_pair.node

            dict_num_add(usage, key=curr_qubit_node, add_value=1)
            dict_num_add(usage, key=curr_main_node, add_value=1)

            concurrents[-1].append(idx_next)
            visited_blocks.add(idx_next)

    return concurrents




def schedule(in_circ, tp_pair_blocks, cat_pair_blocks):
    out_circ = in_circ.copy() # circuit should stay the same, only changing metadata (comm schedule)

    concurrent_cats = greedy_schedule(cat_pair_blocks, is_tp=False) 
    concurrent_tps = greedy_schedule(tp_pair_blocks, is_tp=True)

    # TODO group cat and tp blocks. ~~Join each layer of blocks with EPR prep time (t_EPR) if the node comm is diff~~
    #### RULE for grouping: order should be preserved -- if CX(1,3) comes before CX(1,5) in original circuit. Preserve. 
    # ##### CX(2,4) does not matter,
    ###### Order key: first operation's layer_idx (last op doesn't matter)
    # TODO keep track of data qubits location (dict) and add TP operations as necessary (handles FUSION)
    # ## TODO find out when must EPR time be added (the circuit diagrams in Figure 11-14 aren't consistent) 


    # TODO return list[list[Block] U Comm]
    return out_circ, (concurrent_tps, concurrent_cats)

def map_to_nodes(num_nodes, circ):
    num_qubits = len(circ.all_qubits())
    if num_nodes == 0:
        num_nodes = min(DEFAULT_QUBITS_PER_NODE * num_qubits, num_qubits)

    qubit_to_node, _ = pymetis_partition(circ, num_nodes)
    return qubit_to_node


def trivial_mapping(num_qubits, circ):
    qubit_to_node = dict()
    node_array = []
    qubits_per_node = num_qubits // num_nodes
    for idx, q in enumerate(circ.all_qubits()):
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
    node_map = map_to_nodes(num_nodes, input_circuit)


    aggregation, agg_circuit = aggregate(input_circuit, node_map)
    if not agg_circuit:
        print('Invalid Input Circuit')
        print(input_circuit)
        return

    print(agg_circuit)

    assignments, assigned_circuit = assign(agg_circuit, aggregation)
    print(assigned_circuit)

    # indexing into the list of block *indices* for each pair, using idx
    # using pair_to_ops to get the block details from each (pair, block_idx)
    tp_blocks = aggregation.get_full_block_set(filter=assignments, flip=False)
    cat_blocks = aggregation.get_full_block_set(filter=assignments, flip=True)

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
