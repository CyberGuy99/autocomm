from autocomm_v2.experiment import run_experiment, CircuitGen
BV = CircuitGen.BV
QFT = CircuitGen.QFT
RCA = CircuitGen.RCA

args = {BV: (100, 10, 1), QFT: (300, 30, 1), RCA: (100, 10, 3)}
expected_epr_cnts = {BV: 9, QFT: 1620, RCA: 36}


for func, cnt in sorted(expected_epr_cnts.items(), key=lambda f: f[0].__name__)[:]:
    print(f'Testing {func.__name__} circuit...')
    func_args = args[func] 
    actual_cnt_part, _ = run_experiment(func, *func_args, do_full=False)
    actual_cnt_full, _ = run_experiment(func, *func_args, do_full=True)
    assert actual_cnt_full == actual_cnt_part == cnt, f'Assert Failed: actual_full ({actual_cnt_full}) == actual_part ({actual_cnt_part}) == expected ({cnt})'

print('Success.')
