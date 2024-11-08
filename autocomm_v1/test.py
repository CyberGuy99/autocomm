from experiment import run_experiment, CircuitGen
BV = CircuitGen.BV
QFT = CircuitGen.QFT
RCA = CircuitGen.RCA

args = {BV: (100, 10, 1), QFT: (300, 30, 1), RCA: (100, 10, 3)}
expected_epr_cnts = {BV: 9, QFT: 1620, RCA: 36}


for func, cnt in sorted(expected_epr_cnts.items(), key=lambda f: f[0].__name__)[2:]:
    func_args = args[func] 
    actual_cnt, _ = run_experiment(func, *func_args, verbose=False)
    assert actual_cnt == cnt, f'actual ({actual_cnt}) != expected ({cnt})'

print('Success.')
