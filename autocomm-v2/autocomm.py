from typing import Union

from gate_util import *
from commute_func import *
from merge_func import *

from gate_util import Gate, GateBlock, gateblock_list_str

# assume gates are formed of CX and single-qubit gates. It is okay to have other gates if related rules are defined
def comm_aggregate(gate_list:list[Gate], qubit_node_mapping:list[int], allow_gate_pattern:bool=True, refine_iter_cnt:int=3, check_commute_func=commute_func_right):
    if allow_gate_pattern == True:
        gate_list = pattern_merged_circ(gate_list)
    new_gate_block_list = consecutive_merge(gate_list, qubit_node_mapping)
    new_gate_block_list = linear_merge_iter(new_gate_block_list, qubit_node_mapping, refine_iter_cnt, check_commute_func)                    
    return new_gate_block_list

def _comm_block_tag(source_qb:int, target_node:int, block_gates:list[Gate], qubit_node_mapping:list[int]):
    _state = []
    _remote_gates:list[int] = []
    for glidx, glocal in enumerate(block_gates):
        glqb = glocal.qubits
        if len(glqb) == 2:
            if glqb[0] == source_qb:
                _state.append(1)
            elif glqb[1] == source_qb:
                _state.append(-1)
            if qubit_node_mapping[glqb[0]] != qubit_node_mapping[glqb[1]]:
                _remote_gates.append(glidx)
    use_cat_comm = True
    # if equal to abs(len(state)) check for any single qubit gates on the control qubit before confirming
    if sum(_state) == len(_state):
        for ii in range(len(_remote_gates)-1):
            # check all gates between iith remote gate and ii+1 th gate
            for jj in range(_remote_gates[ii]+1,_remote_gates[ii+1]):
                gjj = block_gates[jj]
                gjjqb = gjj.qubits
                if len(gjjqb) == 1 and gjjqb[0] == source_qb:
                    if gjj.type not in ["RZ", "Z", "X"]: # cat-comm permissible gates
                        use_cat_comm = False
                        break
            if not use_cat_comm:
                break
    # This case happens if all remote gates have the source as the Target, not the Control 
    ### must swap every control and target to permit a cat-comm
    elif sum(_state) == -len(_state):
        for jj in _remote_gates:
            gjj = block_gates[jj]
            # This equality is always true in the first iteration
            if gjj.type != block_gates[_remote_gates[0]].type:
                use_cat_comm = False
                break
            if gjj.type not in ["CX", "CZ"]:
                use_cat_comm = False
                break
        # same check as above but additional check for the first remote gate
        if use_cat_comm:
            for ii in range(len(_remote_gates)-1):
                for jj in range(_remote_gates[ii]+1,_remote_gates[ii+1]):
                    gjj = block_gates[jj]
                    gjjqb = gjj.qubits
                    if len(gjjqb) == 1 and gjjqb[0] == source_qb:
                        if block_gates[_remote_gates[0]].type == "CX":
                            if gjj.type not in ["RX", "Z", "X"]:
                                use_cat_comm = False
                                break
                        elif block_gates[_remote_gates[0]].type == "CZ":
                            if gjj.type not in ["RZ", "Z", "X"]:
                                use_cat_comm = False
                                break
                if not use_cat_comm:
                    break
    else:
        use_cat_comm = False

    num_comm_gates = sum([1 for g in block_gates if g.is_comm(qubit_node_mapping)])
    return GateBlock(source=source_qb, targets=[target_node]*num_comm_gates, \
                      gates=block_gates, is_cat=use_cat_comm)

def comm_assign(gate_block_list:list[GateBlock], qubit_node_mapping:list[int]):
    assigned_gate_block_list: list[GateBlock] = []
    for gb in gate_block_list:
        if type(gb) is GateBlock:
            if gb.empty_source_target():
                # Find first gate in block that is 2-qubit and non-local
                for _g in gb.gates:
                    _gqb = _g.qubits
                    if len(_gqb) == 2:
                        if qubit_node_mapping[_gqb[0]] != qubit_node_mapping[_gqb[1]]:
                            break
                # assuming all gates in the gateblock have the same source, target
                source_qb, target_node = _gqb[0], qubit_node_mapping[_gqb[1]]
                new_comm_block: list[GateBlock] = _comm_block_tag(source_qb, target_node, gb.gates, qubit_node_mapping)
                if new_comm_block[0].is_cat:
                    # if cat, append
                    assigned_gate_block_list.append(new_comm_block)
                else:
                    # if not cat, try swapping source,target and checking again
                    source_qb, target_node = _gqb[1], qubit_node_mapping[_gqb[0]]
                    new_comm_block: list[GateBlock] = _comm_block_tag(source_qb, target_node, gb.gates, qubit_node_mapping)
                    assigned_gate_block_list.append(new_comm_block)
            else:
                source_qb, target_node = gb.get_source_target(qubit_node_mapping)
                new_comm_block = _comm_block_tag(source_qb, target_node, gb.gates, qubit_node_mapping)
                assigned_gate_block_list.append(new_comm_block)
        else:
            assigned_gate_block_list.append(gb)
    
    sanity_check_count(assigned_gate_block_list, qubit_node_mapping)
    return assigned_gate_block_list

def comm_schedule(assigned_gate_block_list:list[Union[Gate, GateBlock]], qubit_node_mapping:list[int], latency_metric:dict[str,float]=None, refine_iter_cnt:int=3, check_commute_func=commute_func_right):
    if latency_metric == None:
        latency_metric = {"1Q":0.1,"CX":1,"CZ":1,"CRZ":2.2,"MS":5,"EP":12,"CB":1}
    assigned_gate_block_list = tp_comm_merge_iter(assigned_gate_block_list, qubit_node_mapping, refine_iter_cnt, check_commute_func)
    # start scheduling
    # [dq0, ..., dq(n-1)] where n is num qubits
    dqb_list = [f"dq{i}" for i in range(len(qubit_node_mapping))]
    node_count = max(qubit_node_mapping) + 1

    # [cq0-0, cq0-1, ..., cqN-0, cqN-1] where N is num nodes
    cqb_list = [f"cq{i}-{j}" for j in [0,1] for i in range(node_count)]
    qb_slot = {}
    for qb in dqb_list+cqb_list:
        qb_slot[qb] = 0
    epr_cnt = 0

    for gb in assigned_gate_block_list:
        if type(gb) is GateBlock:
            if gb.is_cat: # cat-comm
                source, target_node = gb.get_source_target(qubit_node_mapping)
                source_node = qubit_node_mapping[source]
                scqb_idx = 0
                if qb_slot[f"cq{source_node}-{0}"] > qb_slot[f"cq{source_node}-{1}"]:
                    scqb_idx = 1
                tcqb_idx = 0
                if qb_slot[f"cq{target_node}-{0}"] > qb_slot[f"cq{target_node}-{1}"]:
                    tcqb_idx = 1
                # do cat-comm
                # EP
                scqb = f"cq{source_node}-{scqb_idx}"
                tcqb = f"cq{target_node}-{tcqb_idx}"
                source_qb = f"dq{source}"
                qb_slot[scqb] = max(qb_slot[scqb],qb_slot[tcqb]) + latency_metric["EP"]
                qb_slot[tcqb] = qb_slot[scqb]
                # CX
                # TODO why is qb_slot[dq{target}] not checked here?
                qb_slot[source_qb] = max(qb_slot[source_qb],qb_slot[scqb]) + latency_metric["CX"]
                qb_slot[scqb] = qb_slot[source_qb]
                # Measure and correction
                qb_slot[scqb] += latency_metric["MS"]
                qb_slot[tcqb] = max(qb_slot[tcqb],qb_slot[scqb]+latency_metric["CB"])+latency_metric["1Q"]
                # main body
                source_qb = tcqb # NOTE after the CAT-Comm, the source qb is transferred to the target node comm qubit
                for glocal in gb.gates:
                    glqb = glocal.qubits
                    if len(glqb) == 1:
                        if glqb[0] == source:
                            qb_slot[source_qb] += latency_metric["1Q"]
                        else:
                            qb_slot[f"dq{glqb[0]}"] += latency_metric["1Q"]
                    elif len(glqb) == 2:
                        ctrl, tgt = glqb
                        ctrl_qb = f"dq{ctrl}"
                        tgt_qb = f"dq{tgt}"
                        if glocal.type in ["CX", "CZ"]:
                            twoq_latency = latency_metric["CX"]
                        elif glocal.type in ["CRZ"]:
                            twoq_latency = latency_metric["CRZ"]
                        else:
                            pass
                        if ctrl == source:
                            qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[tgt_qb]) + twoq_latency
                            qb_slot[tgt_qb] = qb_slot[source_qb]
                        elif tgt == source:
                            qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[ctrl_qb]) + twoq_latency
                            qb_slot[ctrl_qb] = qb_slot[source_qb]
                        else:
                            qb_slot[ctrl_qb] = max(qb_slot[ctrl_qb], qb_slot[tgt_qb]) + twoq_latency
                            qb_slot[tgt_qb] = qb_slot[ctrl_qb]
                # finish up
                source_qb = f"dq{source}"
                qb_slot[tcqb] += latency_metric["1Q"]+latency_metric["MS"]
                qb_slot[source_qb] = max(qb_slot[source_qb],qb_slot[tcqb]+latency_metric["CB"])+latency_metric["1Q"]
                epr_cnt += 1
            else: # Tp-comm
                # do parallel
                if len(gb.targets_no_dups) == 1:
                    source, target_node = gb.get_source_target(qubit_node_mapping)
                    source_node = qubit_node_mapping[source]
                    scqb_idx = 0
                    if qb_slot[f"cq{source_node}-{0}"] > qb_slot[f"cq{source_node}-{1}"]:
                        scqb_idx = 1
                    tcqb_idx = 0
                    if qb_slot[f"cq{target_node}-{0}"] > qb_slot[f"cq{target_node}-{1}"]:
                        tcqb_idx = 1
                    source_qb = f"dq{source}"
                    scqb = f"cq{source_node}-{scqb_idx}"
                    tcqb = f"cq{target_node}-{tcqb_idx}"
                    # do tp-comm
                    # EP
                    qb_slot[scqb] = max(qb_slot[scqb],qb_slot[tcqb]) + latency_metric["EP"]
                    qb_slot[tcqb] = qb_slot[scqb]
                    # CX
                    qb_slot[source_qb] = max(qb_slot[source_qb],qb_slot[scqb]) + latency_metric["CX"]
                    qb_slot[scqb] = qb_slot[source_qb]
                    # H
                    qb_slot[source_qb] = qb_slot[source_qb] + latency_metric["1Q"]
                    # M
                    qb_slot[source_qb] = qb_slot[source_qb] + latency_metric["MS"]
                    qb_slot[scqb] = qb_slot[scqb] + latency_metric["MS"]
                    qb_slot[tcqb] = max(qb_slot[tcqb],qb_slot[scqb]+latency_metric["CB"]) + latency_metric["1Q"]
                    qb_slot[tcqb] = max(qb_slot[tcqb],qb_slot[source_qb]+latency_metric["CB"]) + latency_metric["1Q"]
                    qb_slot[source_qb] += latency_metric["1Q"] # reset
                    # main body
                    source_qb = tcqb
                    for glocal in gb.gates:
                        glqb = glocal.qubits
                        if len(glqb) == 1:
                            if glqb[0] == source:
                                qb_slot[source_qb] += latency_metric["1Q"]
                            else:
                                qb_slot[f"dq{glqb[0]}"] += latency_metric["1Q"]
                        elif len(glqb) == 2:
                            ctrl, tgt = glqb
                            ctrl_qb = f"dq{ctrl}"
                            tgt_qb = f"dq{tgt}"
                            if glocal.type in ["CX", "CZ"]:
                                twoq_latency = latency_metric["CX"]
                            elif glocal.type in ["CRZ"]:
                                twoq_latency = latency_metric["CRZ"]
                            else:
                                pass
                            if ctrl == source:
                                qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[tgt_qb]) + twoq_latency
                                qb_slot[tgt_qb] = qb_slot[source_qb]
                            elif tgt == source:
                                qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[ctrl_qb]) + twoq_latency
                                qb_slot[ctrl_qb] = qb_slot[source_qb]
                            else:
                                qb_slot[ctrl_qb] = max(qb_slot[ctrl_qb], qb_slot[tgt_qb]) + twoq_latency
                                qb_slot[tgt_qb] = qb_slot[ctrl_qb]
                    # finish up
                    source_qb = f"dq{source}"
                    tcqb_new = f"cq{target_node}-{1-tcqb_idx}"
                    qb_slot[scqb] = max(qb_slot[scqb],qb_slot[tcqb_new]) + latency_metric["EP"]
                    qb_slot[tcqb_new] = qb_slot[scqb]
                    qb_slot[source_qb] = max(qb_slot[source_qb],qb_slot[scqb]) + 3*latency_metric["CX"]
                    qb_slot[scqb] = qb_slot[source_qb]
                    qb_slot[tcqb_new] = max(qb_slot[tcqb_new],qb_slot[tcqb]) + latency_metric["CX"]
                    qb_slot[tcqb] = qb_slot[tcqb_new]
                    qb_slot[tcqb_new] += latency_metric["MS"]
                    qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[tcqb_new]+latency_metric["CB"]) + latency_metric["1Q"]
                    qb_slot[tcqb] += latency_metric["1Q"] + latency_metric["MS"]
                    qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[tcqb]+latency_metric["CB"]) + latency_metric["1Q"]
                    epr_cnt += 2
                # do serial
                if len(gb.targets_no_dups) > 1:
                    source = gb.source
                    source_node = qubit_node_mapping[source]
                    prev_target = qubit_node_mapping[source]
                    scqb_idx_prev = 0
                    if qb_slot[f"cq{source_node}-{0}"] > qb_slot[f"cq{source_node}-{1}"]:
                        scqb_idx_prev = 1
                    source_qb_prev = f"dq{source}"
                    
                    for tnidx, target_node in enumerate(gb.targets_no_dups):
                        source_node = prev_target
                        prev_target = target_node

                        scqb_idx = scqb_idx_prev
                        tcqb_idx = 0
                        if qb_slot[f"cq{target_node}-{0}"] > qb_slot[f"cq{target_node}-{1}"]:
                            tcqb_idx = 1
                        scqb_idx_prev = 1 - tcqb_idx
                        
                        source_qb = source_qb_prev
                        scqb = f"cq{source_node}-{scqb_idx}"
                        tcqb = f"cq{target_node}-{tcqb_idx}"
                        source_qb_prev = tcqb

                        # do tp-comm
                        # EP
                        qb_slot[scqb] = max(qb_slot[scqb],qb_slot[tcqb]) + latency_metric["EP"]
                        qb_slot[tcqb] = qb_slot[scqb]
                        # CX
                        qb_slot[source_qb] = max(qb_slot[source_qb],qb_slot[scqb]) + latency_metric["CX"]
                        qb_slot[scqb] = qb_slot[source_qb]
                        # H
                        qb_slot[source_qb] = qb_slot[source_qb] + latency_metric["1Q"]
                        # M
                        qb_slot[source_qb] = qb_slot[source_qb] + latency_metric["MS"]
                        qb_slot[scqb] = qb_slot[scqb] + latency_metric["MS"]
                        qb_slot[tcqb] = max(qb_slot[tcqb],qb_slot[scqb]+latency_metric["CB"]) + latency_metric["1Q"]
                        qb_slot[tcqb] = max(qb_slot[tcqb],qb_slot[source_qb]+latency_metric["CB"]) + latency_metric["1Q"]
                        qb_slot[source_qb] += latency_metric["1Q"] # reset
                        epr_cnt += 1

                        # main body
                        source_qb = tcqb
                        glocal = gb.gates[tnidx]
                        glqb = glocal.qubits
                        if len(glqb) == 1:
                            if glqb[0] == source:
                                qb_slot[source_qb] += latency_metric["1Q"]
                            else:
                                qb_slot[f"dq{glqb[0]}"] += latency_metric["1Q"]
                        elif len(glqb) == 2:
                            ctrl, tgt = glqb
                            ctrl_qb = f"dq{ctrl}"
                            tgt_qb = f"dq{tgt}"
                            if glocal.type in ["CX", "CZ"]:
                                twoq_latency = latency_metric["CX"]
                            elif glocal.type in ["CRZ"]:
                                twoq_latency = latency_metric["CRZ"]
                            else:
                                pass
                            if ctrl == source:
                                qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[tgt_qb]) + twoq_latency
                                qb_slot[tgt_qb] = qb_slot[source_qb]
                            elif tgt == source:
                                qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[ctrl_qb]) + twoq_latency
                                qb_slot[ctrl_qb] = qb_slot[source_qb]
                            else:
                                qb_slot[ctrl_qb] = max(qb_slot[ctrl_qb], qb_slot[tgt_qb]) + twoq_latency
                                qb_slot[tgt_qb] = qb_slot[ctrl_qb]
                    # finish up
                    source_qb = f"dq{source}"
                    source_node = qubit_node_mapping[source]
                    scqb_idx = 0
                    if qb_slot[f"cq{source_node}-{0}"] > qb_slot[f"cq{source_node}-{1}"]:
                        scqb_idx = 1
                    scqb = f"cq{source_node}-{scqb_idx}"
                    tcqb_new = f"cq{target_node}-{1-tcqb_idx}"

                    qb_slot[scqb] = max(qb_slot[scqb],qb_slot[tcqb_new]) + latency_metric["EP"]
                    qb_slot[tcqb_new] = qb_slot[scqb]
                    qb_slot[source_qb] = max(qb_slot[source_qb],qb_slot[scqb]) + 3*latency_metric["CX"]
                    qb_slot[scqb] = qb_slot[source_qb]
                    qb_slot[tcqb_new] = max(qb_slot[tcqb_new],qb_slot[tcqb]) + latency_metric["CX"]
                    qb_slot[tcqb] = qb_slot[tcqb_new]
                    qb_slot[tcqb_new] += latency_metric["MS"]
                    qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[tcqb_new]+latency_metric["CB"]) + latency_metric["1Q"]
                    qb_slot[tcqb] += latency_metric["1Q"] + latency_metric["MS"]
                    qb_slot[source_qb] = max(qb_slot[source_qb], qb_slot[tcqb]+latency_metric["CB"]) + latency_metric["1Q"]
                    epr_cnt += 1
        else:
            assert type(gb) is Gate
            gqb = gb.qubits
            if len(gqb) == 1:
                qb_slot[f"dq{gqb[0]}"] += latency_metric["1Q"]
            elif len(gqb) == 2: # must be local
                qb0, qb1 = gqb
                if gb.type in ["CX", "CZ"]:
                    qb_slot[f"dq{qb0}"] = max(qb_slot[f"dq{qb0}"], qb_slot[f"dq{qb1}"]) + latency_metric["CX"]
                    qb_slot[f"dq{qb1}"] = qb_slot[f"dq{qb0}"]
                elif gb.type in ["CRZ"]:
                    qb_slot[f"dq{qb0}"] = max(qb_slot[f"dq{qb0}"], qb_slot[f"dq{qb1}"]) + latency_metric["CRZ"]
                    qb_slot[f"dq{qb1}"] = qb_slot[f"dq{qb0}"]
    all_latency =  max(qb_slot.values())

    #blocks = [g for g in assigned_gate_block_list if type(g) is GateBlock]
    return epr_cnt, all_latency, assigned_gate_block_list


if __name__ == "__main__":
    print(comm_assign([[[],[["CX",[0,1]],["RX",[0]],["RX",[1]],["CX",[0,1]]]]],[0,2]))
