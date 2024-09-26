import cirq

class Pair:
    # expecting circuit to only have line qubits
    qubit: cirq.LineQubit = None
    node_qubit: cirq.LineQubit = None
    node: int = -1
    qubit_node: int = -1
    is_ctrl: bool = False
    layer_idx: int = -1

    def __init__(self, qubit: cirq.LineQubit, node: int, node_qubit: cirq.LineQubit, qubit_node: int, is_ctrl: bool, layer_idx: int):
        self.qubit = qubit
        self.node_qubit = node_qubit

        self.node = node
        self.qubit_node = qubit_node

        self.is_ctrl = is_ctrl
        self.layer_idx = layer_idx
    
    def is_qubit_control(self):
        return self.is_ctrl
    
    def get_q_node(self):
        return self.qubit_node
    
    def get_ctrl_q(self):
        return self.qubit if self.is_ctrl else self.node_qubit

    def get_targ_q(self):
        return self.node_qubit if self.is_ctrl else self.qubit
    
    def get_op_tuple(self):
        return (self.get_ctrl_q(), self.get_targ_q())

class Block:
    pairs: list[Pair] = [] # collection of 2-qubit ops and their metadat
    def __init__(self, pairs):
        self.pairs = pairs

    def get_q_and_node(self):
        return (self.pairs[0].qubit, self.pairs[0].node) 

    def get_pair(self):
        # model_pair = self.pairs[0]
        # return Pair(model_pair.qubit, model_pair.node, model_pair.node_qubit, model_pair.qubit_node, False, -1)
        return self.pairs[0]

    def start_pair_idx(self):
        return self.pairs[0].layer_idx

    def end_pair_idx(self):
        return self.pairs[-1].layer_idx



class PairAggregation:
    q_and_node: tuple(cirq.LineQubit, int) = None
    blocks: list[Block] = []
    pairs: list[Pair] = []

    
    def __init__(self, pair, blocks, pairs):
        self.pair = pair
        self.blocks = blocks
        self.pairs = pairs
    
    def get_full_blocks(self):
        return [ [pair for pair in block] for block in self.blocks]



class PairAggregationSet:
    # clustered_blocks: dict[ tuple(cirq.LineQubit,int), list[Block] ] = dict() 
    # clustered_pairs: dict[ tuple(cirq.LineQubit,int), list[Pair] ] = dict() # KEY: (q, node), VALUE: list of Pairs

    # KEY: (q, node), VALUE: PairAggregation
    aggregations: dict[ tuple(cirq.LineQubit,int), PairAggregation ] = dict()

    def __init__(self, clustered_blocks, clustered_pairs):
        for pair_key in clustered_blocks:
            if pair_key not in clustered_pairs:
                print(f'Unusual Key: {pair_key}')
                continue

            self.aggregations[pair_key] = PairAggregation(q_and_node=pair_key, \
                blocks=clustered_blocks[pair_key], pairs=clustered_pairs[pair_key])

    
    def get_full_block_set(self, filter=None, flip=False):
        if not filter:
            filter = dict( {q_and_node : True for q_and_node in self.aggregations} )
        if flip:
            filter = dict( {not filter[q_and_node] for q_and_node in self.aggregations} )

        return [agg.get_full_blocks() for q_and_node, agg in self.aggregations.items() if filter[q_and_node]]


    def get_keyed_blocks(self):
        return dict( {pair_key: agg.blocks for pair_key, agg in self.aggregations.items()} )
