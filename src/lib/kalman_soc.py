# kalman_soc.py
import math
from collections import deque

class KalmanSOC:
    """
    Extended Kalman Filter for SOC estimation.
    Works on ESP32 / RP2040 with MicroPython.
    """

    def __init__(self, config):
        """
        config (dict):
            capacity_ah      : float
            num_cells        : int
            initial_soc      : 0.0–1.0
            R0               : pack IR at 25°C (Ohm)
            Q                : process noise covariance (2×2)
            R                : voltage measurement noise variance
            ocv_table        : list[(v_cell, soc)]  # per-cell
        """
        self.C = config['capacity_ah']
        self.n = config['num_cells']
        self.dt = config.get('sampling_interval', 1.0)

        # ---- OCV lookup (scaled to pack) ----
        per_cell = config.get('ocv_table',
            [(3.60,1.0),(3.40,0.95),(3.35,0.80),(3.325,0.60),
             (3.30,0.40),(3.275,0.20),(3.20,0.10),(2.50,0.0)])
        self.pack_ocv = [(v*self.n, s) for v,s in per_cell]

        # ---- State & covariance ----
        self.x = [float(config.get('initial_soc',0.5)), 0.0]   # [SOC, R_offset]
        self.P = config.get('P0', [[0.01,0.0],[0.0,1e-6]])    # initial uncertainty

        # ---- Noise matrices ----
        self.Q = config.get('Q', [[1e-6,0.0],[0.0,1e-9]])     # SOC drift, R drift
        self.R = config.get('R', 0.01)                       # voltage noise (V²)

        # ---- Internal resistance (temp-compensated if you pass T) ----
        self.R0 = config['R0']                               # pack IR at ref temp
        self.T_ref = config.get('T_ref', 25.0)
        self.alpha = config.get('alpha', 0.004)              # 0.4 %/°C

    # ------------------------------------------------------------------
    # Helper: linear interpolation of OCV(SOC)
    # ------------------------------------------------------------------
    def _ocv(self, soc):
        tbl = self.pack_ocv
        if soc >= 1.0: return tbl[0][0]
        if soc <= 0.0: return tbl[-1][0]
        for i in range(len(tbl)-1):
            v1,s1 = tbl[i]
            v2,s2 = tbl[i+1]
            if s2 <= soc <= s1:
                return v1 + (v2-v1)*(soc-s1)/(s2-s1)
        return tbl[-1][0]

    # ------------------------------------------------------------------
    # Jacobians
    # ------------------------------------------------------------------
    def _F(self):
        """∂f/∂x  (2×2)"""
        return [[1.0, 0.0],
                [0.0, 1.0]]

    def _H(self, soc):
        """∂h/∂x  (1×2)  – derivative of voltage w.r.t. SOC and R_offset"""
        # dOCV/dSOC ≈ ΔOCV/ΔSOC over a tiny window
        eps = 1e-6
        dOCV = (self._ocv(soc+eps) - self._ocv(soc-eps)) / (2*eps)
        # dV/dR_offset = -I  (because V = OCV - (R0+R_offset)*I )
        return [dOCV, -self.last_I]

    # ------------------------------------------------------------------
    # Prediction step
    # ------------------------------------------------------------------
    def predict(self, I):
        """I: signed current (A), positive = charging"""
        self.last_I = I
        soc = self.x[0]

        # ---- state transition f(x,u) ----
        soc_new = soc - (I * self.dt) / (self.C * 3600.0)
        soc_new = max(0.0, min(1.0, soc_new))

        self.x[0] = soc_new                 # R_offset unchanged

        # ---- covariance propagation ----
        F = self._F()
        P = self.P
        self.P = [[F[0][0]*P[0][0]*F[0][0] + F[0][1]*P[1][0]*F[0][0],
                   F[0][0]*P[0][1]*F[1][1] + F[0][1]*P[1][1]*F[1][1]],
                  [F[1][0]*P[0][0]*F[0][0] + F[1][1]*P[1][0]*F[0][0],
                   F[1][0]*P[0][1]*F[1][1] + F[1][1]*P[1][1]*F[1][1]]]

        # add process noise
        self.P[0][0] += self.Q[0][0]
        self.P[1][1] += self.Q[1][1]

    # ------------------------------------------------------------------
    # Update step (voltage measurement)
    # ------------------------------------------------------------------
    def update(self, V_meas, T=None):
        """
        V_meas : measured pack voltage (V)
        T      : temperature (°C) – optional for IR compensation
        """
        soc = self.x[0]
        R_offset = self.x[1]

        # temperature-compensated resistance
        if T is not None:
            R = self.R0 * (1.0 + self.alpha*(T - self.T_ref))
        else:
            R = self.R0
        R_total = R + R_offset

        # ---- predicted measurement h(x) ----
        V_pred = self._ocv(soc) - self.last_I * R_total

        # ---- innovation ----
        y = V_meas - V_pred

        # ---- Jacobian H ----
        H = self._H(soc)                     # 1×2 list

        # ---- innovation covariance S ----
        S = (H[0]*self.P[0][0]*H[0] + H[0]*self.P[0][1]*H[1] +
             H[1]*self.P[1][0]*H[0] + H[1]*self.P[1][1]*H[1]) + self.R

        # ---- Kalman gain K (2×1) ----
        K0 = (self.P[0][0]*H[0] + self.P[0][1]*H[1]) / S
        K1 = (self.P[1][0]*H[0] + self.P[1][1]*H[1]) / S
        K = [K0, K1]

        # ---- state correction ----
        self.x[0] += K[0] * y
        self.x[1] += K[1] * y
        self.x[0] = max(0.0, min(1.0, self.x[0]))

        # ---- covariance update ----
        P11 = self.P[0][0] - K[0]*(H[0]*self.P[0][0] + H[1]*self.P[0][1])
        P12 = self.P[0][1] - K[0]*(H[0]*self.P[1][0] + H[1]*self.P[1][1])
        P21 = self.P[1][0] - K[1]*(H[0]*self.P[0][0] + H[1]*self.P[0][1])
        P22 = self.P[1][1] - K[1]*(H[0]*self.P[1][0] + H[1]*self.P[1][1])
        self.P = [[P11, P12], [P21, P22]]

        return self.x[0] * 100.0          # return SOC in %

    # ------------------------------------------------------------------
    # Convenience: full step (current → voltage → SOC)
    # ------------------------------------------------------------------
    def step(self, I, V, T=None):
        self.predict(I)
        return self.update(V, T)