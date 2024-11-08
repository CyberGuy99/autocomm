from gate_util import remove_repeated_gates, Gate

def commute_func_right(lblk:list[Gate], rblk:list[Gate]): # right to left
    is_commute = False
    if lblk == [] or rblk == []:
        return True, -1, -1, lblk, rblk
    
    new_lblk = [] # the lblk after moving after rblk
    for lgidx, lg in enumerate(reversed(lblk)):
        cur_check_point = [lg]
        new_rblk = []
        for rgidx, rg in enumerate(rblk):
            rgtype = rg.type
            new_check_point = []
            new_rg = rg
            for cur_lg in reversed(cur_check_point):
                lgtype = cur_lg.type
                lgqb = cur_lg.qubits
                rgqb = rg.qubits
                # ONE QUBIT R GATE COMPARED W/ ALL 
                if lgtype in ["RZ"]:
                    if rgtype in ["RZ", "Z"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg) # clone tuple
                    elif rgtype in ["RX"]:
                        if lgqb[0] != rgqb[0]:
                            is_commute = True
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                    elif rgtype in ["X"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            # same RZ gate but flip the angle (-1)
                            new_check_point.append(cur_lg.transform(params=[-cur_lg.params[0]]))
                        else:
                            new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["H"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            # same params but change basis to RX
                            new_check_point.append(cur_lg.transform(type="RX"))
                        else:
                            new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["CX", "CRX"]:
                        is_commute = True
                        if lgqb[0] not in rgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[0] == rgqb[0]: # on control line
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                is_commute = False
                    elif rgtype in ["CZ","CRZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                elif lgtype in ["RX"]:
                    if rgtype in ["RX", "X"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["RZ"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            is_commute = False
                        else:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                    elif rgtype in ["Z"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            new_check_point.append(cur_lg.transform(params=[-cur_lg.params[0]]))
                        else:
                            new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["H"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            new_check_point.append(cur_lg.transform(type="RZ"))
                        else:
                            new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["CX", "CRX"]:
                        is_commute = True
                        if lgqb[0] not in rgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[0] == rgqb[1]: # on target line
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                is_commute = False
                    elif rgtype in ["CZ","CRZ"]:
                        is_commute = True
                        if lgqb[0] not in rgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            is_commute = False
                ### H compared with ALL
                elif lgtype in ["H"]:
                    if rgtype in ["RX"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        if lgqb[0] == rgqb[0]:
                            new_rg = (rg.transform(type="RZ"))
                        else:
                            new_rg = (rg)
                    elif rgtype in ["RZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        if lgqb[0] == rgqb[0]:
                            new_rg = (rg.transform(type="RX"))
                        else:
                            new_rg = (rg)
                    elif rgtype in ["Z"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        if lgqb[0] == rgqb[0]:
                            new_rg = (rg.transform(type="X"))
                        else:
                            new_rg = (rg)
                    elif rgtype in ["X"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        if lgqb[0] == rgqb[0]:
                            new_rg = (rg.transform(type="Z"))
                        else:
                            new_rg = (rg)
                    elif rgtype in ["H"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["CX", "CRX"]:
                        is_commute = True
                        if lgqb[0] not in rgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[0] == rgqb[1]: # on target line
                                new_check_point.append(cur_lg)
                                new_rg = (rg.transform(type=rgtype[:-1]+"Z"))
                            else:
                                is_commute = False # TODO could commute, current not implemented
                    elif rgtype in ["CZ","CRZ"]:
                        is_commute = True
                        if lgqb[0] not in rgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[0] == rgqb[1]: # on target line
                                new_check_point.append(cur_lg)
                                new_rg = (rg.transform(type=rgtype[:-1]+"X"))
                            else:
                                is_commute = False # TODO could commute, current not implemented
                # ONE QUBIT Pauli GATE COMPARED W/ ALL 
                elif lgtype == "X":
                    if rgtype in ["RX"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["RZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        if lgqb[0] == rgqb[0]:
                            new_rg = (rg.transform(type="RZ", params=[-param for param in rg.params]))
                        else:
                            new_rg = (rg)
                    elif rgtype in ["Z"]: # a global phase
                        is_commute = True
                        new_check_point.append(cur_lg)
                        if lgqb[0] == rgqb[0]:
                            new_rg = (rg.transform(type="Z"))
                            # TODO Doesn't this do the same thing as (rg)
                        else:
                            new_rg = (rg)
                    elif rgtype in ["X"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["H"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            new_check_point.append(cur_lg.transform(type="Z"))
                        else:
                            new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["CX", "CRX"]:
                        is_commute = True
                        if lgqb[0] not in rgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[0] == rgqb[1]: # on target line
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else: # on control line # NOTE Different than the RX case
                                # add X or RX gate to the target qubit (before the RG) to counter the LG
                                new_check_point.append(cur_lg)
                                new_check_point.append(rg.transform(type=rgtype[1:],qubits=rg.qubits[1:],params=[-param for param in rg.params]))
                                new_rg = (rg)
                    elif rgtype in ["CZ","CRZ"]:
                        is_commute = True
                        if lgqb[0] not in rgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else: # NOTE Different than the RX case (just set is_commute to False)
                            if lgqb[0] == rgqb[1]: # on target line
                                new_check_point.append(cur_lg)
                                if rgtype != "CRZ":
                                    # Transform X into a Z gate
                                    new_check_point.append(rg.transform(type=rgtype[1:],qubits=rg.qubits[:1],params=[-param for param in rg.params]))
                                else:
                                    is_commute = False
                                new_rg = (rg)
                            else: # on control line
                                new_check_point.append(cur_lg)
                                new_check_point.append(rg.transform(type=rgtype[1:],qubits=rg.qubits[1:],params=[-param for param in rg.params]))
                                new_rg = (rg)                          
                elif lgtype == "Z":
                    if rgtype in ["RZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["RX"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        if lgqb[0] == rgqb[0]:
                            new_rg = (rg.transform(type="RX",  params=[-param for param in rg.params]))
                        else:
                            new_rg = (rg)
                    elif rgtype in ["X"]: # a global phase
                        is_commute = True
                        new_check_point.append(cur_lg)
                        if lgqb[0] == rgqb[0]:
                            new_rg = rg.transform(type="X")
                        else:
                            new_rg = (rg)
                    elif rgtype in ["Z"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["H"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            new_check_point.append(cur_lg.transform(type="X"))
                        else:
                            new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["CZ", "CRZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["CX","CRX"]:
                        is_commute = True
                        if lgqb[0] not in rgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[0] == rgqb[1]: # on target line
                                new_check_point.append(cur_lg)
                                if rgtype == "CX":
                                    new_check_point.append(rg.transform(type="Z",qubits=rg.qubits[:1],params=[-param for param in rg.params]))
                                new_rg = (rg)
                            else: # on control line
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                # 2 QUBIT Pauli GATE COMPARED W/ ALL 
                elif lgtype in ["CX"]:
                    if rgtype in ["RX"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if rgqb[0] == lgqb[1]: # RX Targets the Target
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                is_commute = False
                    elif rgtype in ["RZ"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if rgqb[0] == lgqb[0]: # RZ Targets the Control
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                is_commute = False
                    elif rgtype in ["Z"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if rgqb[0] == lgqb[0]:
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                # Z on the Control before the controlled Op
                                new_check_point.append(cur_lg.transform(type='Z', qubits=lgqb[:1]))
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                    elif rgtype in ["X"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if rgqb[0] == lgqb[1]:
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                # X on the Target before the controlled Op
                                new_check_point.append(cur_lg.transform(type='X', qubits=lgqb[1:]))
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                    elif rgtype in ["H"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[1] == rgqb[0]:
                                # Transforms CX into CZ
                                new_check_point.append(cur_lg.transform(type="CZ"))
                                new_rg = (rg)
                            else:
                                is_commute = False # not implemented
                    elif rgtype in ["CX", "CRX"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        elif lgqb[0] == rgqb[1]:
                            is_commute = False
                        elif lgqb[1] == rgqb[0]:
                            is_commute = False
                        else: # same target or completely different
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                    elif rgtype in ["CZ","CRZ"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            if lgqb[1] != rgqb[1]: # SAME Control DIFF Target
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                new_check_point.append(cur_lg) # SAME Control SAME Target: flip RG angles
                                new_rg = (rg.transform(params=[-param for param in rg.params]))
                        elif lgqb[0] == rgqb[1]: # RG Targets LG's Control
                            if lgqb[1] != rgqb[0]: # RG Control Diff than LG Target
                                new_check_point.append(cur_lg) # FINE because the CZ/CRZ won't X the LG state
                                new_rg = (rg)
                            else:
                                new_check_point.append(cur_lg)
                                new_rg = (rg.transform(params=[-param for param in rg.params]))
                        elif lgqb[1] == rgqb[0]: # LG Targets RG control (X will affect it)
                            is_commute = False
                        else:
                            is_commute = False
                elif lgtype in ["CZ"]:
                    if rgtype in ["RZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["RX"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            is_commute = False
                    elif rgtype in ["X"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if rgqb[0] == lgqb[0]:
                                new_check_point.append(cur_lg.transform(type='X', qubits=lgqb[1:]))
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                new_check_point.append(cur_lg.transform(type='X', qubits=lgqb[:1]))
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                    elif rgtype in ["Z"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["H"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[1] == rgqb[0]:
                                new_check_point.append(cur_lg.transform(type="CX"))
                            else:
                                new_check_point.append(cur_lg.transform(type="CX", qubits=cur_lg.qubits[::-1]))
                            new_rg = (rg)
                    elif rgtype in ["CZ", "CRZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["CX","CRX"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            if lgqb[1] != rgqb[1]:
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                new_check_point.append(cur_lg)
                                new_rg = (rg.transform(params=[-param for param in rg.params]))
                        elif lgqb[0] == rgqb[1]:
                            is_commute = False
                        elif lgqb[1] == rgqb[0]:
                            if lgqb[0] != rgqb[1]:
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                new_check_point.append(cur_lg)
                                new_rg = (rg.transform(params=[-param for param in rg.params]))
                        else:
                            is_commute = False
                # 2 QUBIT R GATE COMPARED W/ ALL 
                elif lgtype in ["CRZ"]:
                    if rgtype in ["RZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["RX"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            is_commute = False
                    elif rgtype in ["X"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if rgqb[0] == lgqb[0]: # X targets LG Control: Prepend same RZ on target to counter X
                                new_check_point.append(cur_lg.transform(type='RZ', qubits=lgqb[1:], params=[-param for param in cur_lg.params]))
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                is_commute = False
                    elif rgtype in ["Z"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["H"]:
                        is_commute = True
                        if rgqb[0] not in lgqb:
                            new_check_point.append(cur_lg)
                            new_rg = (rg)
                        else:
                            if lgqb[1] == rgqb[0]: # Transform ONLY if H targets LG target
                                new_check_point.append(cur_lg.transform(type="CRX"))
                                new_rg = (rg)
                            else: # o/w all good TODO check this
                                is_commute = True  
                    elif rgtype in ["CZ", "CRZ"]:
                        is_commute = True
                        new_check_point.append(cur_lg)
                        new_rg = (rg)
                    elif rgtype in ["CX"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            if lgqb[1] != rgqb[1]: # SAME Control DIFF Target
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else: # SAME Control SAME Target: flip the params for CRZ (LG)
                                new_check_point.append(cur_lg.transform(params=[-param for param in cur_lg.params]))
                                new_rg = (rg)
                        elif lgqb[0] == rgqb[1]: # CX (RG) Targets the LG Control
                            is_commute = False
                        elif lgqb[1] == rgqb[0]: # LG Targets the CX (RG) Control
                            if lgqb[0] != rgqb[1]: 
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else: # CX (RG) Targets the LG Control
                                is_commute = False
                        else:
                            is_commute = False
                    elif rgtype in ["CRX"]:
                        is_commute = True
                        if lgqb[0] == rgqb[0]:
                            if lgqb[1] != rgqb[1]:
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else: # NOTE STRICTER for CRX if SAME Control and SAME Target
                                is_commute = False
                        elif lgqb[0] == rgqb[1]:
                            is_commute = False
                        elif lgqb[1] == rgqb[0]:
                            if lgqb[0] != rgqb[1]:
                                new_check_point.append(cur_lg)
                                new_rg = (rg)
                            else:
                                is_commute = False
                        else:
                            is_commute = False
                    else: # TODO not implemented
                        pass
                if is_commute is False:
                    return False, lgidx, rgidx, [], []
                else:
                    rg = new_rg
            new_check_point = remove_repeated_gates(new_check_point)
            cur_check_point = new_check_point[::-1]
            new_rblk.append(new_rg)
        rblk = new_rblk
        new_lblk.extend(remove_repeated_gates(new_check_point))
    new_lblk = new_lblk[::-1] ## REVERSES ARRAY (not in-place)
    return True, -1, -1, new_lblk, new_rblk