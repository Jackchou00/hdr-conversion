import numpy as np

def pq_eotf_inverse(linear):
    m1 = 2610 / 4096 * (1 / 4)  # 0.1593017578125
    m2 = 2523 / 4096 * 128      # 78.84375
    c1 = 3424 / 4096            # 0.8359375
    c2 = 2413 / 4096 * 32       # 18.8515625
    c3 = 2392 / 4096 * 32       # 18.6875
    y = np.clip(linear / 10000, 0, 1)
    y_m1 = y ** m1
    numerator = c1 + c2 * y_m1
    denominator = 1 + c3 * y_m1
    pq = (numerator / denominator) ** m2
    return np.clip(pq, 0, 1)
