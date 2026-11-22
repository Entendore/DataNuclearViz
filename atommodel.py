"""
Advanced Computational Atomic & Nuclear Model — v6
==================================================
Upgrades from v5:
  * Decay path drawn on Chart of Nuclides (arrows showing α/β steps)
  * Mass Number (A) spinbox synced with Neutrons (N)
  * Cached Valley of Stability (eliminates UI lag)
  * Skip Animation feature (Esc key or input change aborts animation)
  * Refactored decay chain logic into coordinate generator
"""

import sys
import math
import time
import os
import re
from dataclasses import dataclass
from typing import Tuple, Dict, List, Optional, Generator

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QSpinBox, QPushButton, QLabel, QComboBox,
    QScrollArea, QSplitter, QStatusBar, QFileDialog, QLineEdit, QGridLayout
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# =============================================================
# Physical constants
# =============================================================
M_P      = 938.272
M_N      = 939.565
M_E      = 0.511
M_ALPHA  = 3727.379
U_AMU    = 931.494
A0_BOHR  = 0.529               # Å
ALPHA_FS = 1.0 / 137.036

# SEMF coefficients
A_V, A_S, A_C, A_A, A_P = 15.8, 18.3, 0.714, 23.2, 12.0
A_W = 36.0                     # Wigner energy coefficient
LAMBDA_W = 10.0                # Wigner damping factor

# α-particle binding energy
B_ALPHA = 2 * M_P + 2 * M_N - M_ALPHA

# Magic numbers
MAGIC_P = {2, 8, 20, 28, 50, 82, 114}
MAGIC_N = {2, 8, 20, 28, 50, 82, 126, 184}
MAGIC_ALL = MAGIC_P | MAGIC_N

# Mass differences
D_M_NPE = M_N - M_P - M_E       # +0.782 MeV  (β⁻)
D_M_PEN = M_P - M_N + M_E       # -0.782 MeV  (EC)

# =============================================================
# Element table
# =============================================================
ELEMENTS: List[Tuple[str, str, int]] = [
    ("n","neutron",1), ("H","hydrogen",1), ("He","helium",4), ("Li","lithium",7),
    ("Be","beryllium",9), ("B","boron",11), ("C","carbon",12), ("N","nitrogen",14),
    ("O","oxygen",16), ("F","fluorine",19), ("Ne","neon",20), ("Na","sodium",23),
    ("Mg","magnesium",24), ("Al","aluminum",27), ("Si","silicon",28), ("P","phosphorus",31),
    ("S","sulfur",32), ("Cl","chlorine",35), ("Ar","argon",40), ("K","potassium",39),
    ("Ca","calcium",40), ("Sc","scandium",45), ("Ti","titanium",48), ("V","vanadium",51),
    ("Cr","chromium",52), ("Mn","manganese",55), ("Fe","iron",56), ("Co","cobalt",59),
    ("Ni","nickel",58), ("Cu","copper",63), ("Zn","zinc",64), ("Ga","gallium",69),
    ("Ge","germanium",74), ("As","arsenic",75), ("Se","selenium",80), ("Br","bromine",79),
    ("Kr","krypton",84), ("Rb","rubidium",85), ("Sr","strontium",88), ("Y","yttrium",89),
    ("Zr","zirconium",90), ("Nb","niobium",93), ("Mo","molybdenum",98), ("Tc","technetium",98),
    ("Ru","ruthenium",102), ("Rh","rhodium",103), ("Pd","palladium",106), ("Ag","silver",107),
    ("Cd","cadmium",114), ("In","indium",115), ("Sn","tin",120), ("Sb","antimony",121),
    ("Te","tellurium",130), ("I","iodine",127), ("Xe","xenon",132), ("Cs","cesium",133),
    ("Ba","barium",138), ("La","lanthanum",139), ("Ce","cerium",140), ("Pr","praseodymium",141),
    ("Nd","neodymium",144), ("Pm","promethium",145), ("Sm","samarium",152), ("Eu","europium",153),
    ("Gd","gadolinium",158), ("Tb","terbium",159), ("Dy","dysprosium",164), ("Ho","holmium",165),
    ("Er","erbium",166), ("Tm","thulium",169), ("Yb","ytterbium",174), ("Lu","lutetium",175),
    ("Hf","hafnium",180), ("Ta","tantalum",181), ("W","tungsten",184), ("Re","rhenium",187),
    ("Os","osmium",192), ("Ir","iridium",193), ("Pt","platinum",195), ("Au","gold",197),
    ("Hg","mercury",202), ("Tl","thallium",205), ("Pb","lead",208), ("Bi","bismuth",209),
    ("Po","polonium",209), ("At","astatine",210), ("Rn","radon",222), ("Fr","francium",223),
    ("Ra","radium",226), ("Ac","actinium",227), ("Th","thorium",232), ("Pa","protactinium",231),
    ("U","uranium",238), ("Np","neptunium",237), ("Pu","plutonium",244), ("Am","americium",243),
    ("Cm","curium",248), ("Bk","berkelium",247), ("Cf","californium",251), ("Es","einsteinium",252),
    ("Fm","fermium",257), ("Md","mendelevium",258), ("No","nobelium",259), ("Lr","lawrencium",262),
    ("Rf","rutherfordium",267), ("Db","dubnium",268), ("Sg","seaborgium",271), ("Bh","bohrium",272),
    ("Hs","hassium",270), ("Mt","meitnerium",276), ("Ds","darmstadtium",281), ("Rg","roentgenium",282),
    ("Cn","copernicium",285), ("Nh","nihonium",286), ("Fl","flerovium",289), ("Mc","moscovium",290),
    ("Lv","livermorium",293), ("Ts","tennessine",294), ("Og","oganesson",294),
]

# =============================================================
# Helpers
# =============================================================
def _shell_term(x: int, magic_set: set) -> float:
    if x == 0: return 0.0
    if x in magic_set: return +0.10
    dist = min(abs(x - m) for m in magic_set)
    return -0.10 * math.sin(math.pi * dist / 12) ** 2 * math.exp(-dist / 20)

def _beta2_term(x: int, magic_set: set) -> float:
    if x == 0 or x in magic_set: return 0.0
    nearest = min(magic_set, key=lambda m: abs(m - x))
    sign = +1 if x > nearest else -1
    dist = abs(x - nearest)
    return sign * 0.20 * math.sin(math.pi * dist / 12) ** 2

def _filled_below(n: int) -> int:
    return sum(2 * k * k for k in range(1, n))

def _slater_Z_eff(Z: int) -> float:
    if Z <= 1: return 1.0
    n = min(max(1, math.ceil(math.sqrt(Z / 2))), 7)
    same_group = max(Z - _filled_below(n), 1)
    inner = _filled_below(n) - _filled_below(n - 1) if n > 1 else 0
    deeper = _filled_below(n - 1) if n > 1 else 0
    S = 0.35 * max(same_group - 1, 0) + 0.85 * inner + 1.00 * deeper
    return max(Z - S, 1.0)

def _fmt_log10sec(log10_t: Optional[float]) -> str:
    if log10_t is None: return "—"
    if log10_t < -9:     return "< 1 ns"
    if log10_t < -6:     return f"~ {10**log10_t*1e9:.2f} ns"
    if log10_t < -3:     return f"~ {10**log10_t*1e6:.2f} µs"
    if log10_t < 0:      return f"~ {10**log10_t*1e3:.2f} ms"
    if log10_t < 1.78:   return f"~ {10**log10_t:.2f} s"
    if log10_t < 3.56:   return f"~ {10**log10_t/60:.2f} min"
    if log10_t < 4.94:   return f"~ {10**log10_t/3600:.2f} h"
    if log10_t < 8.50:   return f"~ {10**log10_t/3.156e7:.3e} yr"
    return f"~ 10^{log10_t:.1f} yr"

# =============================================================
# Snapshot
# =============================================================
@dataclass
class DecayStep:
    Z: int
    N: int
    mode: str  # "Start", "α", "β⁻", "β⁺", "SF", "Stable"

@dataclass
class IsotopeSnapshot:
    Z: int; N: int; A: int
    symbol: str; name: str
    B: float; BA: float; ME: float; pairing: float; wigner: float
    beta2: float
    spin_parity: str; E2plus: float
    Q_beta_minus: float; Q_beta_plus: float; Q_alpha: float
    S_n: float; S_p: float
    hl_alpha: str; hl_beta: str; hl_sf: str; logft_class: str
    dominant_mode: str
    capture_sigma_rel: float
    k_shell_radius: float; valence_radius: float; ionization: float
    stability_status: str
    qcd_scale: str
    decay_chain_html: str
    decay_chain_steps: List[DecayStep]

# =============================================================
# Physics engine
# =============================================================
class NuclearAtomicModel:
    def __init__(self, Z: int, N: int):
        self.Z = max(int(Z), 0)
        self.N = max(int(N), 0)
        self.A = self.Z + self.N
        self._cached: Optional[Tuple[float, float, float, float]] = None

    def binding(self) -> Tuple[float, float, float, float]:
        if self._cached is not None:
            return self._cached
        if self.A == 0:
            self._cached = (0.0, 0.0, 0.0, 0.0)
            return self._cached
        Z, N, A = self.Z, self.N, self.A
        
        E_vol   =  A_V * A
        E_surf  = -A_S * A ** (2/3)
        E_coul  = -A_C * Z * (Z - 1) / A ** (1/3)
        E_asym  = -A_A * (A - 2*Z) ** 2 / A
        E_wig   = -A_W * math.exp(-abs(N - Z) / LAMBDA_W)
        
        if A % 2 == 1:
            delta = 0.0
        else:
            sign = +1 if (Z % 2 == 0 and N % 2 == 0) else -1
            delta = sign * A_P / math.sqrt(A)
            
        E_shell = (_shell_term(Z, MAGIC_P) + _shell_term(N, MAGIC_N)) * A ** (2/3)
        B = max(E_vol + E_surf + E_coul + E_asym + E_wig + delta + E_shell, 0.0)
        ME = (Z * M_P + N * M_N - B) - A * U_AMU
        self._cached = (B, ME, delta, E_wig)
        return self._cached

    @staticmethod
    def qcd_scale() -> str:
        return "Λ_QCD ≈ 200 MeV (strong-confinement scale)"

    def beta2(self) -> float:
        if self.A == 0: return 0.0
        return (_beta2_term(self.Z, MAGIC_P) + _beta2_term(self.N, MAGIC_N)) / 2

    def quantum_states(self) -> Tuple[str, float]:
        if self.A == 0: return "—", 0.0
        if self.Z % 2 == 0 and self.N % 2 == 0: spin = "0⁺"
        elif self.Z % 2 == 1 and self.N % 2 == 1: spin = "1⁺ to 7⁻ (odd-odd)"
        else: spin = "1/2⁺ to 9/2⁻ (typical odd-A)"
        b2 = self.beta2()
        E2 = 40 * self.A ** (-1/3) if abs(b2) < 0.05 else 1200.0 / (self.A * b2 * b2)
        return spin, max(E2, 0.01)

    def decay_q_values(self) -> Tuple[float, float, float, float, float]:
        if self.A == 0: return 0.0, 0.0, 0.0, 0.0, 0.0
        B_p = self.binding()[0]
        B_d  = NuclearAtomicModel(self.Z + 1, self.N - 1).binding()[0]
        Q_bm = D_M_NPE + (B_d - B_p)
        B_d2 = NuclearAtomicModel(self.Z - 1, self.N + 1).binding()[0]
        Q_EC = D_M_PEN + (B_d2 - B_p)
        Q_bp = Q_EC - 2 * M_E
        B_d3 = NuclearAtomicModel(self.Z - 2, self.N - 2).binding()[0]
        Q_alpha = B_ALPHA + B_d3 - B_p
        S_n = B_p - NuclearAtomicModel(self.Z, self.N - 1).binding()[0] if self.N > 0 else 0.0
        S_p = B_p - NuclearAtomicModel(self.Z - 1, self.N).binding()[0] if self.Z > 0 else 0.0
        return Q_bm, Q_bp, Q_alpha, S_n, S_p

    def _fermi_integral(self, Q_beta: float, Z_d: int, branch: str) -> float:
        if Q_beta <= 0: return 0.0
        W0 = Q_beta / M_E + 1.0
        N = 50
        h = (W0 - 1.0) / N
        total = 0.0
        for i in range(N + 1):
            W = 1.0 + i * h
            p = math.sqrt(max(W * W - 1.0, 0.0))
            eta = Z_d * ALPHA_FS / p if branch == "β⁻" else -Z_d * ALPHA_FS / p
            expo = 2 * math.pi * eta
            if abs(expo) < 60:
                F = expo / (1 - math.exp(-expo))
            else:
                F = 2 * math.pi * eta if eta > 0 else 0.0
            integrand = p * W * (W0 - W)**2 * F
            if i == 0 or i == N:
                total += integrand
            elif i % 2 == 1:
                total += 4 * integrand
            else:
                total += 2 * integrand
        return total * h / 3.0

    def sf_half_life_log10s(self) -> Optional[float]:
        if self.A < 200 or self.Z < 82: return None
        return -5.57 * (self.Z**2 / self.A) + 221.2

    def decay_rates_log10(self) -> Tuple[str, str, str, str, str]:
        Q_bm, Q_bp, Q_alpha, _, _ = self.decay_q_values()

        log_t_alpha = None
        if Q_alpha > 0 and self.Z >= 2 and self.A >= 4:
            a_vs, b_vs, c_vs = 1.66175, -8.5166, -0.20228
            if self.Z % 2 == 0 and self.N % 2 == 0: d_vs = -33.9069
            elif self.Z % 2 == 1 and self.N % 2 == 1: d_vs = -29.5800
            else: d_vs = -31.9069
            log_t_alpha = (a_vs * self.Z + b_vs) / math.sqrt(Q_alpha) + c_vs * self.Z + d_vs

        log_t_beta = None
        branch = ""
        logft_class = "—"
        if Q_bm > 0 and Q_bm >= Q_bp:
            Q_beta, branch, Z_d = Q_bm, "β⁻", self.Z + 1
        elif Q_bp > 0:
            Q_beta, branch, Z_d = Q_bp, "β⁺/EC", max(self.Z - 1, 1)
            
        if branch:
            if self.Z % 2 == 0 and self.N % 2 == 0: log_ft, logft_class = 7.5, "1st forbidden (ee → oo)"
            elif self.Z % 2 == 1 and self.N % 2 == 1: log_ft, logft_class = 7.0, "1st forbidden (oo → ee)"
            else: log_ft, logft_class = 5.0, "Allowed (Gamow–Teller)"

            f = self._fermi_integral(Q_beta, Z_d, branch)
            t_beta = (10 ** log_ft) / max(f, 1e-30)
            log_t_beta = math.log10(max(t_beta, 1e-30))

        log_t_sf = self.sf_half_life_log10s()

        modes = []
        if log_t_alpha is not None: modes.append(("α", log_t_alpha))
        if log_t_beta is not None:  modes.append(("β", log_t_beta))
        if log_t_sf is not None:    modes.append(("SF", log_t_sf))
        
        dominant_mode = min(modes, key=lambda x: x[1])[0] if modes else "Stable"

        hl_alpha = _fmt_log10sec(log_t_alpha) if log_t_alpha is not None else "Stable to α"
        hl_beta = _fmt_log10sec(log_t_beta) + f"  [{branch}]" if log_t_beta is not None else "Stable to β"
        hl_sf = _fmt_log10sec(log_t_sf) if log_t_sf is not None else "—"

        return hl_alpha, hl_beta, hl_sf, logft_class, dominant_mode

    def reactor_capture(self) -> float:
        if self.A == 0: return 0.0
        base = 500 + 1000 * math.exp(-0.05 * self.A) if (self.N % 2 != 0 and self.A > 50) else 2 + 10 * math.exp(-0.02 * self.A)
        return min(base / 15.0, 100.0)

    def electron_cloud(self) -> Tuple[float, float, float]:
        if self.Z == 0: return 0.0, 0.0, 0.0
        Z_eff_k = max(self.Z - 0.3, 1.0)
        Zc  = min(self.Z, 136)
        rel = 1.0 / math.sqrt(max(1.0 - (Zc * ALPHA_FS) ** 2, 1e-4))
        r_k = A0_BOHR / Z_eff_k * rel
        n_v = min(max(1, math.ceil(math.sqrt(self.Z / 2))), 7)
        Z_eff_v = _slater_Z_eff(self.Z)
        r_v = A0_BOHR * n_v * n_v / Z_eff_v
        ion = 13.6 * (Z_eff_v / n_v) ** 2
        return r_k, r_v, min(ion, 150000)

    def stability(self) -> Tuple[float, float, str]:
        if self.A == 0: return 0.0, 0.0, "—"
        B_p = self.binding()[0]
        S_n = B_p - NuclearAtomicModel(self.Z, self.N - 1).binding()[0] if self.N > 0 else 0.0
        S_p = B_p - NuclearAtomicModel(self.Z - 1, self.N).binding()[0] if self.Z > 0 else 0.0
        Z_opt = self.A / (2 + 0.0154 * self.A ** (2/3))
        N_opt = self.A - Z_opt
        dN = self.N - N_opt
        if abs(dN) < 1.5:        status = "β-stable"
        elif dN > 0:             status = "Neutron-rich (β⁻ emitter)"
        else:                    status = "Proton-rich (β⁺/EC emitter)"
        return S_n, S_p, status

    def get_decay_steps(self, max_steps=10) -> List[DecayStep]:
        Z, N = self.Z, self.N
        steps = [DecayStep(Z, N, "Start")]
        
        for _ in range(max_steps):
            m = NuclearAtomicModel(Z, N)
            _, _, _, _, dom = m.decay_rates_log10()
            
            if dom == "Stable":
                steps.append(DecayStep(Z, N, "Stable"))
                break
            elif dom == "α":
                steps.append(DecayStep(Z, N, "α"))
                Z, N = Z - 2, N - 2
            elif dom == "β":
                Q_bm, Q_bp, _, _, _ = m.decay_q_values()
                if Q_bm > 0 and Q_bm >= Q_bp:
                    steps.append(DecayStep(Z, N, "β⁻"))
                    Z, N = Z + 1, N - 1
                else:
                    steps.append(DecayStep(Z, N, "β⁺"))
                    Z, N = Z - 1, N + 1
            elif dom == "SF":
                steps.append(DecayStep(Z, N, "SF"))
                break
            else:
                break
        else:
            steps.append(DecayStep(Z, N, "..."))
            
        return steps

    def snapshot(self) -> IsotopeSnapshot:
        B, ME, delta, wig = self.binding()
        beta2 = self.beta2()
        spin, E2 = self.quantum_states()
        Q_bm, Q_bp, Q_alpha, S_n, S_p = self.decay_q_values()
        hl_a, hl_b, hl_sf, logft_cls, dom_mode = self.decay_rates_log10()
        cap = self.reactor_capture()
        r_k, r_v, ion = self.electron_cloud()
        _, _, status = self.stability()
        
        steps = self.get_decay_steps()
        
        # Build HTML from steps
        html_parts = []
        for i, step in enumerate(steps):
            sym = ELEMENTS[step.Z][0] if step.Z < len(ELEMENTS) else "?"
            A = step.Z + step.N
            if i == 0 or step.mode == "Stable":
                if step.mode == "Stable":
                    html_parts.append(f"<b style='color:#00ffcc;'>{A}{sym}</b> (Stable)")
                else:
                    html_parts.append(f"{A}{sym}")
            elif step.mode == "...":
                html_parts.append("...")
            elif step.mode == "SF":
                html_parts.append(f" → <span style='color:#ff5555;'>SF</span> (Fission)")
            else:
                color = "#ffcf57" if step.mode == "α" else ("#00ddff" if step.mode == "β⁻" else "#ff5555")
                html_parts.append(f" → <span style='color:{color};'>{step.mode}</span> → {A}{sym}")
                
        chain_html = " ".join(html_parts)
        
        sym, name, _ = ELEMENTS[self.Z] if self.Z < len(ELEMENTS) else ("?", "unknown", 0)
        return IsotopeSnapshot(
            Z=self.Z, N=self.N, A=self.A, symbol=sym, name=name,
            B=B, BA=B/self.A if self.A else 0.0, ME=ME, pairing=delta, wigner=wig,
            beta2=beta2, spin_parity=spin, E2plus=E2,
            Q_beta_minus=Q_bm, Q_beta_plus=Q_bp, Q_alpha=Q_alpha,
            S_n=S_n, S_p=S_p,
            hl_alpha=hl_a, hl_beta=hl_b, hl_sf=hl_sf, logft_class=logft_cls,
            dominant_mode=dom_mode, capture_sigma_rel=cap,
            k_shell_radius=r_k, valence_radius=r_v, ionization=ion,
            stability_status=status, qcd_scale=self.qcd_scale(),
            decay_chain_html=chain_html, decay_chain_steps=steps
        )

# =============================================================
# Matplotlib canvas
# =============================================================
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=3, dpi=100, polar=False):
        fig = Figure(figsize=(width, height), dpi=dpi)
        fig.set_facecolor('#2b2b2b')
        super().__init__(fig)
        self.fig = fig
        self.ax = fig.add_subplot(111, projection='polar' if polar else None)
        self.ax.set_facecolor('#2b2b2b')
        self._style(self.ax, polar)

    @staticmethod
    def _style(ax, polar=False):
        ax.tick_params(colors='white')
        try:
            ax.xaxis.label.set_color('white')
            ax.yaxis.label.set_color('white')
        except Exception: pass
        ax.title.set_color('white')
        for s in ax.spines.values():
            s.set_edgecolor('#888')
        if not polar:
            ax.grid(True, alpha=0.25, color='white')

# =============================================================
# Main window
# =============================================================
SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

class AtomModelApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Computational Atomic & Nuclear Model — v6")
        self.resize(1400, 900)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # ----- LEFT -----
        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(8, 8, 8, 8)

        self.header = QLabel("—")
        self.header.setAlignment(Qt.AlignCenter)
        self.header.setStyleSheet(
            "font-size: 22pt; font-weight: 600; color: #ffcf57;"
            " padding: 10px; background: #1f1f1f; border-radius: 6px;"
            " border: 1px solid #444;"
        )
        left.addWidget(self.header)

        # Top Controls
        ctrl_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("e.g. U-238...")
        self.search_edit.setFixedWidth(120)
        self.search_edit.returnPressed.connect(self.search_isotope)
        ctrl_row.addWidget(self.search_edit)
        
        ctrl_row.addWidget(QLabel("Element:"))
        self.elem_combo = QComboBox()
        for i, (sym, name, _) in enumerate(ELEMENTS):
            self.elem_combo.addItem(f"{i:>3}: {sym:<3}  ({name})", i)
        self.elem_combo.setCurrentIndex(92)
        self.elem_combo.currentIndexChanged.connect(self.on_element_changed)
        ctrl_row.addWidget(self.elem_combo, 2)
        
        ctrl_row.addWidget(QLabel("A:"))
        self.a_spin = QSpinBox()
        self.a_spin.setRange(1, 300)
        self.a_spin.setValue(238)
        self.a_spin.valueChanged.connect(self.on_a_changed)
        ctrl_row.addWidget(self.a_spin)
        
        ctrl_row.addWidget(QLabel("N:"))
        self.n_spin = QSpinBox()
        self.n_spin.setRange(0, 300)
        self.n_spin.setValue(146)
        self.n_spin.valueChanged.connect(self.on_n_changed)
        ctrl_row.addWidget(self.n_spin)
        
        self.anim_btn = QPushButton("▶ Animate")
        self.anim_btn.setStyleSheet("background-color: #803658; font-weight: bold;")
        self.anim_btn.clicked.connect(self.run_animation)
        ctrl_row.addWidget(self.anim_btn)
        left.addLayout(ctrl_row)

        # 2x2 Plot Grid
        self.canvas_be       = MplCanvas(self, width=4, height=3)
        self.canvas_parabola = MplCanvas(self, width=4, height=3)
        self.canvas_shape    = MplCanvas(self, width=4, height=3, polar=True)
        self.canvas_chart    = MplCanvas(self, width=4, height=3)

        plots_grid = QGridLayout()
        plots_grid.setSpacing(5)
        plots_grid.addWidget(self.canvas_be, 0, 0)
        plots_grid.addWidget(self.canvas_parabola, 0, 1)
        plots_grid.addWidget(self.canvas_shape, 1, 0)
        plots_grid.addWidget(self.canvas_chart, 1, 1)
        left.addLayout(plots_grid, 3)

        btn_row = QHBoxLayout()
        self.copy_btn = QPushButton("📋  Copy Report")
        self.copy_btn.clicked.connect(self.copy_report)
        self.save_btn = QPushButton("💾  Save Plots")
        self.save_btn.clicked.connect(self.save_plots)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch()
        left.addLayout(btn_row)

        splitter.addWidget(left_widget)

        # ----- RIGHT -----
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_scroll.setWidget(right_container)
        self.labels: Dict[str, QLabel] = {}
        self.groups: Dict[str, QGroupBox] = {}

        def create_group(title, fields, html=False):
            grp = QGroupBox(title)
            grp.setObjectName(title)
            grp.setStyleSheet(self._group_style())
            form = QFormLayout()
            form.setSpacing(6)
            for key, tip in fields:
                lbl = QLabel("—")
                lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                lbl.setStyleSheet("color: #00ffcc; font-family: Consolas, Menlo, monospace; font-size: 10pt;")
                lbl.setToolTip(tip)
                if html: lbl.setTextFormat(Qt.RichText)
                form.addRow(f"{key}:", lbl)
                self.labels[key] = lbl
            grp.setLayout(form)
            right_layout.addWidget(grp)
            self.groups[title] = grp

        # Groups
        create_group("Summary", [
            ("Dominant Decay Mode", "Predicted primary decay channel (α, β, or Spontaneous Fission)."),
            ("Decay Path", "Predicted decay chain to stability based on fastest half-lives.")
        ], html=True)

        create_group("1. Fundamental Force", [("QCD Scale", "Confinement scale of QCD.")])
        create_group("2. Bulk Nuclear Mass", [
            ("Binding Energy (MeV)", "Total binding energy from SEMF + Wigner + shell correction."),
            ("B/A (MeV)", "Binding energy per nucleon. Peak ~8.7 at Fe-56."),
            ("Mass Excess (MeV)", "Mass excess vs A·u."),
            ("Pairing Gap (MeV)", "Odd-even pairing term."),
            ("Wigner Energy (MeV)", "N=Z symmetry energy spike."),
        ])
        create_group("3. Nuclear Shape", [("Quadrupole Deformation (β₂)", "Signed β₂. Positive = prolate, negative = oblate.")])
        create_group("4. Quantum States", [
            ("Spin & Parity", "Ground-state spin/parity estimate from pairing."),
            ("First 2⁺ Energy (MeV)", "Estimated first 2⁺ excitation."),
        ])
        create_group("5. Decay Thresholds", [
            ("Q β⁻ (MeV)", "Energy released in β⁻ decay. ✓ ⇒ allowed."),
            ("Q β⁺/EC (MeV)", "Energy released in β⁺ or electron capture."),
            ("Q α (MeV)", "Energy released in α decay."),
        ])
        create_group("6. Decay Rates", [
            ("α Half-life", "Modern Viola–Seaborg formula."),
            ("β Half-life", "Numerical Fermi phase space + logft."),
            ("SF Half-life", "Empirical spontaneous fission estimate (Z>82)."),
            ("logft Class", "Allowed / forbidden transition class."),
        ])
        create_group("7. Reactor Physics", [("Thermal Capture (rel.)", "Relative σ_th index 0–100 (heuristic).")])
        create_group("8. Electron Cloud", [
            ("K-shell Radius (Å)", "Bohr radius of innermost electron (relativistic)."),
            ("Valence Radius (Å)", "Slater-screened outer electron radius."),
            ("Ionization Energy (eV)", "Outer electron ionization estimate."),
        ])

        right_layout.addStretch()
        splitter.addWidget(right_scroll)
        splitter.setSizes([750, 700])

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_lbl = QLabel("Ready")
        sb.addWidget(self.status_lbl, 1)

        # Pre-calculate Valley of Stability to avoid UI lag
        self._valley_A, self._valley_BA = [], []
        self._calculate_valley_cache()

        # Animation Timer
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(40)
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_steps = []
        self.anim_idx = 0
        self.anim_tick = 0
        self.current_snap: Optional[IsotopeSnapshot] = None

        # Shortcuts
        QShortcut(QKeySequence("Return"),  self, activated=self.calculate)
        QShortcut(QKeySequence("Enter"),   self, activated=self.calculate)
        QShortcut(QKeySequence("Esc"),     self, activated=self.skip_animation)

        self.apply_dark_theme()
        self.on_element_changed(92) # Triggers calculation

    def _calculate_valley_cache(self):
        for a_env in range(1, 260):
            best_ba = 0
            for z_env in range(max(1, a_env // 2 - 10), min(a_env, a_env // 2 + 10)):
                n_env = a_env - z_env
                m_env = NuclearAtomicModel(z_env, n_env)
                b_env = m_env.binding()[0]
                if b_env > 0:
                    ba_env = b_env / a_env
                    if ba_env > best_ba:
                        best_ba = ba_env
            if best_ba > 0:
                self._valley_A.append(a_env)
                self._valley_BA.append(best_ba)

    @staticmethod
    def _group_style(active=False) -> str:
        color = "#ffcf57" if active else "#555"
        bg = "#3a3a1f" if active else "#303030"
        return f"""
            QGroupBox {{
                font-weight: 600; border: 2px solid {color}; border-radius: 6px;
                margin-top: 12px; padding-top: 14px; background: {bg};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }}
        """

    def search_isotope(self):
        text = self.search_edit.text().strip().lower()
        if not text: return
        match = re.match(r'^(\d+)[\s\-]+(\d+)$', text)
        if match:
            Z, A = int(match.group(1)), int(match.group(2))
            if 0 <= Z < len(ELEMENTS):
                self.elem_combo.setCurrentIndex(Z)
                self.a_spin.setValue(A)
                return
        match = re.match(r'^([a-zA-Z]{1,2})[\s\-]+(\d+)$', text)
        if match:
            sym, A = match.group(1).capitalize(), int(match.group(2))
            for i, (s, n, _) in enumerate(ELEMENTS):
                if s.lower() == sym.lower():
                    self.elem_combo.setCurrentIndex(i)
                    self.a_spin.setValue(A)
                    return

    def on_element_changed(self, index: int):
        Z = index
        if Z == 0:
            self.a_spin.setValue(1)
            return
        _, _, A_default = ELEMENTS[Z] if Z < len(ELEMENTS) else ("?", "?", 2 * Z)
        self.a_spin.setValue(A_default)

    def on_a_changed(self, A: int):
        Z = self.elem_combo.currentIndex()
        N = max(0, A - Z)
        if self.n_spin.value() != N:
            self.n_spin.blockSignals(True)
            self.n_spin.setValue(N)
            self.n_spin.blockSignals(False)
        self.calculate()

    def on_n_changed(self, N: int):
        Z = self.elem_combo.currentIndex()
        A = Z + N
        if self.a_spin.value() != A:
            self.a_spin.blockSignals(True)
            self.a_spin.setValue(A)
            self.a_spin.blockSignals(False)
        self.calculate()

    def set_inputs_enabled(self, enabled: bool):
        for w in [self.elem_combo, self.n_spin, self.a_spin, self.search_edit, self.anim_btn]:
            w.setEnabled(enabled)

    # ==========================================
    # ANIMATION ENGINE
    # ==========================================
    def run_animation(self):
        if self.anim_timer.isActive(): return
        
        Z = self.elem_combo.currentIndex()
        N = self.n_spin.value()
        self.current_snap = NuclearAtomicModel(Z, N).snapshot()
        
        for key, lbl in self.labels.items():
            lbl.setText("...")
        for title, grp in self.groups.items():
            grp.setStyleSheet(self._group_style(False))
            
        for canvas in [self.canvas_be, self.canvas_parabola, self.canvas_shape, self.canvas_chart]:
            canvas.ax.clear()
            canvas.draw()
            
        self.set_inputs_enabled(False)
        self.status_lbl.setText("Running animation... (Esc to skip)")
        
        self.anim_steps = [
            ("1. Fundamental Force", 800, self._anim_step1),
            ("2. Bulk Nuclear Mass", 1500, self._anim_step2),
            ("3. Nuclear Shape", 1200, self._anim_step3),
            ("4. Quantum States", 800, self._anim_step4),
            ("5. Decay Thresholds", 1200, self._anim_step5),
            ("6. Decay Rates", 2000, self._anim_step6),
            ("7. Reactor Physics", 800, self._anim_step7),
            ("8. Electron Cloud", 800, self._anim_step8),
            ("Summary", 1500, self._anim_summary),
        ]
        self.anim_idx = 0
        self.anim_tick = 0
        self.anim_timer.start()

    def skip_animation(self):
        if self.anim_timer.isActive():
            self.anim_timer.stop()
            self.set_inputs_enabled(True)
            self.status_lbl.setText("Animation skipped.")
            self.calculate()

    def _on_anim_tick(self):
        step = self.anim_steps[self.anim_idx]
        title, duration, action = step
        progress = self.anim_tick / (duration / 40.0)
        if progress >= 1.0: progress = 1.0
        
        for t, grp in self.groups.items():
            grp.setStyleSheet(self._group_style(t == title))
            
        action(progress)
        
        self.anim_tick += 1
        if progress >= 1.0:
            self.anim_idx += 1
            self.anim_tick = 0
            if self.anim_idx >= len(self.anim_steps):
                self.anim_timer.stop()
                self.set_inputs_enabled(True)
                self.status_lbl.setText("Animation complete.")
                self.calculate()

    def _anim_step1(self, progress: float):
        self.labels["QCD Scale"].setText(self.current_snap.qcd_scale)
        ax = self.canvas_be.ax
        ax.clear()
        ax.text(0.5, 0.5, "Step 1:\nQCD Confinement Scale\nΛ_QCD ≈ 200 MeV", 
                transform=ax.transAxes, ha='center', va='center', color='white', fontsize=14)
        self.canvas_be.draw()

    def _anim_step2(self, progress: float):
        s = self.current_snap
        self.labels["Binding Energy (MeV)"].setText(f"{s.B:.2f}")
        self.labels["B/A (MeV)"].setText(f"{s.BA:.4f}")
        self.labels["Mass Excess (MeV)"].setText(f"{s.ME:.2f}")
        self.labels["Pairing Gap (MeV)"].setText(f"{s.pairing:.3f}")
        self.labels["Wigner Energy (MeV)"].setText(f"{s.wigner:.3f}")
        
        ax = self.canvas_be.ax
        ax.clear()
        n_max = max(3 * s.Z, 30)
        A_vals, BA_vals = [], []
        for n_it in range(0, n_max + 1):
            m = NuclearAtomicModel(s.Z, n_it)
            B = m.binding()[0]
            if B > 0:
                A_vals.append(s.Z + n_it)
                BA_vals.append(B / (s.Z + n_it))
        
        limit = int(len(A_vals) * progress)
        if limit > 0:
            ax.plot(A_vals[:limit], BA_vals[:limit], color='cyan', lw=1.5)
            ax.scatter([s.A], [s.BA], color='red', s=70, zorder=5)
        ax.set_xlabel('Mass Number A')
        ax.set_ylabel('B/A (MeV)')
        ax.set_title(f'Binding Energy per Nucleon  (Z = {s.Z})')
        ax.grid(True, alpha=0.25, color='white')
        self.canvas_be.draw()

    def _anim_step3(self, progress: float):
        s = self.current_snap
        self.labels["Quadrupole Deformation (β₂)"].setText(f"{s.beta2:+.4f}")
        
        ax = self.canvas_shape.ax
        ax.clear()
        current_beta = s.beta2 * progress
        theta = [i * math.pi / 180 for i in range(361)]
        Y20 = math.sqrt(5 / (16 * math.pi))
        R = [1 + current_beta * Y20 * (3 * math.cos(t) ** 2 - 1) for t in theta]
        color = 'magenta' if s.beta2 >= 0 else 'lime'
        ax.plot(theta, R, color=color, lw=1.8)
        ax.fill(theta, R, color=color, alpha=0.25)
        try: ax.set_ylim(0.5, 1.5)
        except: pass
        ax.set_title(f'β₂ = {current_beta:+.3f}', pad=15)
        self.canvas_shape.draw()

    def _anim_step4(self, progress: float):
        s = self.current_snap
        self.labels["Spin & Parity"].setText(s.spin_parity)
        self.labels["First 2⁺ Energy (MeV)"].setText(f"{s.E2plus:.3f}")

    def _anim_step5(self, progress: float):
        s = self.current_snap
        self.labels["Q β⁻ (MeV)"].setText(f"{s.Q_beta_minus:+.2f}  {'✓' if s.Q_beta_minus>0 else '✗'}")
        self.labels["Q β⁺/EC (MeV)"].setText(f"{s.Q_beta_plus:+.2f}  {'✓' if s.Q_beta_plus >0 else '✗'}")
        self.labels["Q α (MeV)"].setText(f"{s.Q_alpha:+.2f}  {'✓' if s.Q_alpha      >0 else '✗'}")
        
        ax = self.canvas_parabola.ax
        ax.clear()
        A = s.A
        Z_opt = A / (2 + 0.0154 * A**(2/3))
        z_min = max(1, int(Z_opt - 6))
        z_max = min(A, int(Z_opt + 6))
        Zs, MEs = [], []
        for z in range(z_min, z_max + 1):
            m = NuclearAtomicModel(z, A - z)
            _, ME, _, _ = m.binding()
            Zs.append(z)
            MEs.append(ME)
            
        limit = int(len(Zs) * progress)
        if limit > 0:
            ax.plot(Zs[:limit], MEs[:limit], color='cyan', marker='o', ls='-')
            if progress > 0.9:
                ax.scatter([s.Z], [s.ME], color='red', s=100, zorder=5)
        ax.set_xlabel('Proton Number (Z)')
        ax.set_ylabel('Mass Excess (MeV)')
        ax.set_title(f'Mass Parabola (A = {A})')
        ax.grid(True, alpha=0.25, color='white')
        self.canvas_parabola.draw()

    def _anim_step6(self, progress: float):
        s = self.current_snap
        self.labels["α Half-life"].setText(s.hl_alpha)
        self.labels["β Half-life"].setText(s.hl_beta)
        self.labels["SF Half-life"].setText(s.hl_sf)
        self.labels["logft Class"].setText(s.logft_class)
        
        parts = s.decay_chain_steps
        limit = int(len(parts) * progress)
        text = ""
        for i in range(limit):
            step = parts[i]
            sym = ELEMENTS[step.Z][0] if step.Z < len(ELEMENTS) else "?"
            A = step.Z + step.N
            if i == 0:
                text += f"{A}{sym}"
            elif step.mode == "Stable":
                text += f" → <b style='color:#00ffcc;'>Stable</b>"
            elif step.mode == "...":
                text += " → ..."
            elif step.mode == "SF":
                text += f" → <span style='color:#ff5555;'>SF</span>"
            else:
                color = "#ffcf57" if step.mode == "α" else ("#00ddff" if step.mode == "β⁻" else "#ff5555")
                text += f" → <span style='color:{color};'>{step.mode}</span> → {A}{sym}"
                
        if limit < len(parts):
            text += " ▌"
        self.labels["Decay Path"].setText(text)

    def _anim_step7(self, progress: float):
        s = self.current_snap
        self.labels["Thermal Capture (rel.)"].setText(f"{s.capture_sigma_rel:.1f} / 100")

    def _anim_step8(self, progress: float):
        s = self.current_snap
        self.labels["K-shell Radius (Å)"].setText(f"{s.k_shell_radius:.4f}")
        self.labels["Valence Radius (Å)"].setText(f"{s.valence_radius:.4f}")
        self.labels["Ionization Energy (eV)"].setText(f"{s.ionization:.2f}")

    def _anim_summary(self, progress: float):
        s = self.current_snap
        self.labels["Dominant Decay Mode"].setText(f"<b style='color:#ffcf57;'>{s.dominant_mode}</b>")
        self.labels["Decay Path"].setText(s.decay_chain_html)
        self.labels["Beta Stability Status"].setText(s.stability_status)
        self.labels["Sₙ (MeV)"].setText(f"{s.S_n:.2f}")
        self.labels["Sₚ (MeV)"].setText(f"{s.S_p:.2f}")
        
        ax = self.canvas_chart.ax
        ax.clear()
        A_range = range(1, 260)
        Z_stable, N_stable = [], []
        for A in A_range:
            Z_opt = A / (2 + 0.0154 * A**(2/3))
            Z_stable.append(Z_opt)
            N_stable.append(A - Z_opt)
        ax.plot(N_stable, Z_stable, color='lime', lw=2, label='Stability Valley')
        
        for n in MAGIC_N: ax.axhline(n, color='gold', ls=':', alpha=0.3)
        for z in MAGIC_P: ax.axvline(z, color='gold', ls=':', alpha=0.3)
            
        size = 150 * progress
        if size > 0:
            ax.scatter([s.N], [s.Z], color='red', s=size, marker='*', zorder=5, label='Current')
        ax.set_xlabel('Neutrons (N)')
        ax.set_ylabel('Protons (Z)')
        ax.set_title('Chart of Nuclides')
        ax.set_xlim(0, 180)
        ax.set_ylim(0, 120)
        ax.grid(True, alpha=0.15, color='white')
        self.canvas_chart.draw()

    # ==========================================
    # STANDARD CALCULATION (Instant)
    # ==========================================
    def calculate(self):
        if self.anim_timer.isActive(): return
        
        Z = self.elem_combo.currentIndex()
        N = self.n_spin.value()
        snap = NuclearAtomicModel(Z, N).snapshot()

        a_sup = str(snap.A).translate(SUPERSCRIPT) if snap.A > 0 else ""
        self.header.setText(f"{a_sup}{snap.symbol}   (Z={Z}, N={N}, A={snap.A})   —   {snap.name.capitalize()}")

        self.labels["Dominant Decay Mode"].setText(f"<b style='color:#ffcf57;'>{snap.dominant_mode}</b>")
        self.labels["Decay Path"].setText(snap.decay_chain_html)
        self.labels["Beta Stability Status"].setText(snap.stability_status)
        self.labels["Sₙ (MeV)"].setText(f"{snap.S_n:.2f}")
        self.labels["Sₚ (MeV)"].setText(f"{snap.S_p:.2f}")
        self.labels["QCD Scale"].setText(snap.qcd_scale)
        self.labels["Binding Energy (MeV)"].setText(f"{snap.B:.2f}")
        self.labels["B/A (MeV)"].setText(f"{snap.BA:.4f}")
        self.labels["Mass Excess (MeV)"].setText(f"{snap.ME:.2f}")
        self.labels["Pairing Gap (MeV)"].setText(f"{snap.pairing:.3f}")
        self.labels["Wigner Energy (MeV)"].setText(f"{snap.wigner:.3f}")
        self.labels["Quadrupole Deformation (β₂)"].setText(f"{snap.beta2:+.4f}")
        self.labels["Spin & Parity"].setText(snap.spin_parity)
        self.labels["First 2⁺ Energy (MeV)"].setText(f"{snap.E2plus:.3f}")
        self.labels["Q β⁻ (MeV)"].setText(f"{snap.Q_beta_minus:+.2f}  {'✓' if snap.Q_beta_minus>0 else '✗'}")
        self.labels["Q β⁺/EC (MeV)"].setText(f"{snap.Q_beta_plus:+.2f}  {'✓' if snap.Q_beta_plus >0 else '✗'}")
        self.labels["Q α (MeV)"].setText(f"{snap.Q_alpha:+.2f}  {'✓' if snap.Q_alpha      >0 else '✗'}")
        self.labels["α Half-life"].setText(snap.hl_alpha)
        self.labels["β Half-life"].setText(snap.hl_beta)
        self.labels["SF Half-life"].setText(snap.hl_sf)
        self.labels["logft Class"].setText(snap.logft_class)
        self.labels["Thermal Capture (rel.)"].setText(f"{snap.capture_sigma_rel:.1f} / 100")
        self.labels["K-shell Radius (Å)"].setText(f"{snap.k_shell_radius:.4f}")
        self.labels["Valence Radius (Å)"].setText(f"{snap.valence_radius:.4f}")
        self.labels["Ionization Energy (eV)"].setText(f"{snap.ionization:.2f}")

        self.update_plots(Z, N, snap)
        self.status_lbl.setText(f"Calculated {a_sup}{snap.symbol} at {time.strftime('%H:%M:%S')}   Status: {snap.stability_status}")

    def update_plots(self, Z, N, snap):
        # 1) B/A curve
        ax1 = self.canvas_be.ax
        ax1.clear()
        
        # Use cached valley
        ax1.plot(self._valley_A, self._valley_BA, color='white', alpha=0.2, lw=2, label='Valley of Stability')

        A_vals, BA_vals = [], []
        n_max = max(3 * Z, 30)
        for n_it in range(0, n_max + 1):
            m = NuclearAtomicModel(Z, n_it)
            B = m.binding()[0]
            if B > 0:
                A_vals.append(Z + n_it)
                BA_vals.append(B / (Z + n_it))
        if A_vals:
            ax1.plot(A_vals, BA_vals, color='cyan', lw=1.5, label=f'{ELEMENTS[Z][0]} isotopes')
            for A_m in MAGIC_ALL:
                if A_m in A_vals:
                    ax1.axvline(A_m, color='gold', ls=':', alpha=0.3)
        if snap.A > 0 and snap.B > 0:
            ax1.scatter([snap.A], [snap.BA], color='red', s=70, zorder=5, label='Current')
        ax1.set_xlabel('Mass Number A')
        ax1.set_ylabel('B/A (MeV)')
        ax1.set_title(f'Binding Energy per Nucleon  (Z = {Z})')
        ax1.legend(facecolor='#333', edgecolor='#555', labelcolor='white', fontsize=8)
        ax1.grid(True, alpha=0.25, color='white')
        self.canvas_be.draw()

        # 2) Mass Parabola
        ax2 = self.canvas_parabola.ax
        ax2.clear()
        A = snap.A
        if A > 0:
            Z_opt = A / (2 + 0.0154 * A**(2/3))
            z_min = max(1, int(Z_opt - 6))
            z_max = min(A, int(Z_opt + 6))
            Zs, MEs = [], []
            for z in range(z_min, z_max + 1):
                m = NuclearAtomicModel(z, A - z)
                _, ME, _, _ = m.binding()
                Zs.append(z)
                MEs.append(ME)
            ax2.plot(Zs, MEs, color='cyan', marker='o', ls='-')
            ax2.scatter([snap.Z], [snap.ME], color='red', s=100, zorder=5, label='Current')
            ax2.set_xlabel('Proton Number (Z)')
            ax2.set_ylabel('Mass Excess (MeV)')
            ax2.set_title(f'Mass Parabola (A = {A})')
            ax2.legend(facecolor='#333', edgecolor='#555', labelcolor='white', fontsize=8)
            ax2.grid(True, alpha=0.25, color='white')
        self.canvas_parabola.draw()

        # 3) Polar deformation
        ax3 = self.canvas_shape.ax
        ax3.clear()
        beta2 = snap.beta2
        theta = [i * math.pi / 180 for i in range(361)]
        Y20 = math.sqrt(5 / (16 * math.pi))
        R = [1 + beta2 * Y20 * (3 * math.cos(t) ** 2 - 1) for t in theta]
        color = 'magenta' if beta2 >= 0 else 'lime'
        ax3.plot(theta, R, color=color, lw=1.8)
        ax3.fill(theta, R, color=color, alpha=0.25)
        try: ax3.set_ylim(0.5, 1.5)
        except Exception: pass
        kind = "Prolate" if beta2 > 0.02 else ("Oblate" if beta2 < -0.02 else "Spherical")
        ax3.set_title(f'Nuclear Shape  β₂ = {beta2:+.3f}  ({kind})', pad=15)
        ax3.tick_params(colors='white')
        ax3.title.set_color('white')
        self.canvas_shape.draw()

        # 4) Chart of Nuclides with Decay Path
        ax4 = self.canvas_chart.ax
        ax4.clear()
        A_range = range(1, 260)
        Z_stable, N_stable = [], []
        for A in A_range:
            Z_opt = A / (2 + 0.0154 * A**(2/3))
            Z_stable.append(Z_opt)
            N_stable.append(A - Z_opt)
        ax4.plot(N_stable, Z_stable, color='lime', lw=2, label='Stability Valley')
        
        for n in MAGIC_N: ax4.axhline(n, color='gold', ls=':', alpha=0.3)
        for z in MAGIC_P: ax4.axvline(z, color='gold', ls=':', alpha=0.3)
            
        # Draw decay path
        steps = snap.decay_chain_steps
        path_N = [s.N for s in steps]
        path_Z = [s.Z for s in steps]
        if len(path_N) > 1:
            ax4.plot(path_N, path_Z, color='red', lw=2, marker='o', markersize=4, ls='-', zorder=4, label='Decay Path')
            
        ax4.scatter([snap.N], [snap.Z], color='red', s=150, marker='*', zorder=5, label='Current')
        ax4.set_xlabel('Neutrons (N)')
        ax4.set_ylabel('Protons (Z)')
        ax4.set_title('Chart of Nuclides')
        ax4.set_xlim(0, 180)
        ax4.set_ylim(0, 120)
        ax4.legend(facecolor='#333', edgecolor='#555', labelcolor='white', fontsize=8, loc='upper left')
        ax4.grid(True, alpha=0.15, color='white')
        self.canvas_chart.draw()

    def copy_report(self):
        Z = self.elem_combo.currentIndex()
        N = self.n_spin.value()
        s = NuclearAtomicModel(Z, N).snapshot()
        chain_text = re.sub('<[^>]+>', '', s.decay_chain_html)
        lines = [
            f"=== Isotope Report: {s.A}{s.symbol} (Z={s.Z}, N={s.N}) ===",
            f"Name: {s.name}",
            f"Stability: {s.stability_status}",
            f"Dominant Decay Mode: {s.dominant_mode}",
            f"Decay Path: {chain_text}",
            "",
            "Step 1 — Fundamental force",
            f"  {s.qcd_scale}",
            "",
            "Step 2 — Bulk nuclear mass",
            f"  Binding energy     : {s.B:.3f} MeV",
            f"  B/A                : {s.BA:.4f} MeV",
            f"  Mass excess        : {s.ME:.3f} MeV",
            f"  Pairing gap        : {s.pairing:.3f} MeV",
            f"  Wigner energy      : {s.wigner:.3f} MeV",
            "",
            "Step 3 — Nuclear shape",
            f"  β₂                 : {s.beta2:+.4f}",
            "",
            "Step 4 — Quantum states",
            f"  Spin & parity      : {s.spin_parity}",
            f"  First 2⁺ energy    : {s.E2plus:.3f} MeV",
            "",
            "Step 5 — Decay thresholds",
            f"  Q β⁻               : {s.Q_beta_minus:+.3f} MeV",
            f"  Q β⁺/EC            : {s.Q_beta_plus:+.3f} MeV",
            f"  Q α                : {s.Q_alpha:+.3f} MeV",
            "",
            "Step 6 — Decay rates",
            f"  α half-life        : {s.hl_alpha}",
            f"  β half-life        : {s.hl_beta}",
            f"  SF half-life       : {s.hl_sf}",
            f"  logft class        : {s.logft_class}",
            "",
            "Step 7 — Reactor physics",
            f"  Thermal capture (rel.): {s.capture_sigma_rel:.1f} / 100",
            "",
            "Step 8 — Electron cloud",
            f"  K-shell radius     : {s.k_shell_radius:.4f} Å",
            f"  Valence radius     : {s.valence_radius:.4f} Å",
            f"  Ionization energy  : {s.ionization:.2f} eV",
            "",
            "Advanced",
            f"  Sₙ                 : {s.S_n:.3f} MeV",
            f"  Sₚ                 : {s.S_p:.3f} MeV",
            "",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        QApplication.clipboard().setText("\n".join(lines))
        self.status_lbl.setText("Report copied to clipboard.")

    def save_plots(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder: return
        Z = self.elem_combo.currentIndex()
        N = self.n_spin.value()
        sym = ELEMENTS[Z][0]
        prefix = f"{sym}{Z+N}"
        for name, canvas in [("binding", self.canvas_be), ("parabola", self.canvas_parabola), 
                             ("shape", self.canvas_shape), ("chart", self.canvas_chart)]:
            path = os.path.join(folder, f"{prefix}_{name}.png")
            canvas.fig.savefig(path, dpi=150, facecolor='#2b2b2b')
        self.status_lbl.setText(f"Saved 4 plots to {folder}")

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; color: #ddd; }
            QGroupBox { color: #ddd; }
            QComboBox, QSpinBox, QLineEdit {
                background-color: #3c3f41; color: #ddd;
                border: 1px solid #555; border-radius: 4px; padding: 4px;
                min-height: 22px;
            }
            QComboBox QAbstractItemView {
                background: #3c3f41; color: #ddd;
                selection-background-color: #365880;
            }
            QPushButton {
                background-color: #365880; color: white;
                border: 1px solid #555; border-radius: 4px;
                padding: 6px 12px; font-weight: 600;
            }
            QPushButton:hover  { background-color: #4a72a0; }
            QPushButton:pressed{ background-color: #28456b; }
            QPushButton:disabled { background-color: #333; color: #666; }
            QScrollArea { border: none; }
            QLabel { color: #ccc; }
            QStatusBar { background: #1f1f1f; color: #aaa; }
            QSplitter::handle { background: #444; }
            QSplitter::handle:hover { background: #666; }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = AtomModelApp()
    w.show()
    sys.exit(app.exec())