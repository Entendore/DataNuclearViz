import sys
import csv
import math
import random
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QCursor, QFont, QPen
from PySide6.QtWidgets import (QApplication, QMainWindow, QSplitter, QTableWidget, 
                               QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget, 
                               QLabel, QLineEdit, QFileDialog, QMenu, QMessageBox,
                               QHBoxLayout, QTabWidget, QToolTip, QCheckBox, 
                               QComboBox, QStatusBar, QSpinBox, QPushButton, QGridLayout)
from PySide6.QtCharts import (QChart, QChartView, QScatterSeries, QValueAxis, 
                              QLogValueAxis, QLineSeries, QPieSeries, QPieSlice, 
                              QAreaSeries, QBarSeries, QBarSet, QBarCategoryAxis)

# --- Dataset Headers ---
HEADERS = "z,n,name,levelEnergy(MeV),halflife,halflifeUnit,halflifeUncertainty,spinAndParity,decayMode,branchingRatio,branchingRatioUncertainty,massExcess(keV),massExcessUncertainty,betaMinus,betaMinusUncertainty,electronCapture,electronCaptureUncertainty,positronEmission,positronEmissionUncertainty,neutronSeparationEnergy,neutronSeparationEnergyUncertainty,protonSeparationEnergy,protonSeparationEnergyUncertainty,alpha,alphaUncertainty,deltaAlpha,deltaAlphaUncertainty,twoNeutronSeparationEnergy,twoNeutronSeparationEnergyUncertainty,twoProtonSeparationEnergy,twoProtonSeparationEnergyUncertainty,doubleBetaMinus,doubleBetaMinusUncertainty,doubleElectronCapture,doubleElectronCaptureUncertainty,electronCaptureOneProtonEmission,electronCaptureOneProtonEmissionUncertainty,betaMinusOneNeutronEmission,betaMinusOneNeutronEmissionUncertainty,betaMinusTwoNeutronEmission,betaMinusTwoNeutronEmissionUncertainty,bindingEnergy,bindingEnergyUncertainty,bindingEnergyLDMFit,bindingEnergyLDMFitUncertainty,pairingGap,pairingGapUncertainty,firstExcitedStateEnergy,firstExcitedStateEnergyUncertainty,firstTwoPlusEnergy,firstTwoPlusEnergyUncertainty,firstThreeMinusEnergy,firstThreeMinusEnergyUncertainty,firstFourPlusEnergy,firstFourPlusEnergyUncertainty,firstFourPlusOverFirstTwoPlusEnergy,firstFourPlusOverFirstTwoPlusEnergyUncertainty,quadrupoleDeformation,quadrupoleDeformationUncertainty,BE4DBE2,BE4DBE2Uncertainty,thermalNeutronCapture,thermalNeutronFission,FY235U,FY235UUncertainty,FY239Pu,FY239PuUncertainty,FY252Cf,FY252CfUncertainty,FY238U,FY238UUncertainty,FY241U,FY241UUncertainty,cFY235U,cFY235UUncertainty,cFY239Pu,cFY239PuUncertainty,cFY252Cf,cFY252CfUncertainty,cFY238U,cFY238UUncertainty,cFY241U,cFY241UUncertainty,secondTwoPlusEnergy,secondTwoPlusEnergyUncertainty"

DEFAULT_DATA = [
    "0,1,Neutron,0,608.9,s,0.3,1/2+,β⁻,100,,8.07E+3,4.40E-4,7.82E+2,4.00E-4,,,,,,,,,,,,,,,,,,,,,,,0.0,0.0,-2.48E+4,0.0,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,"
]

HIDDEN_COLS = [h for h in HEADERS.split(',') if 'Uncertainty' in h or h in ['deltaAlpha', 'bindingEnergyLDMFit', 'pairingGap', 'firstExcitedStateEnergy', 'firstThreeMinusEnergy', 'firstFourPlusEnergy', 'firstFourPlusOverFirstTwoPlusEnergy', 'BE4DBE2', 'thermalNeutronCapture', 'thermalNeutronFission', 'secondTwoPlusEnergy', 'branchingRatio', 'levelEnergy(MeV)']]

MAGIC_NUMBERS = [2, 8, 20, 28, 50, 82, 126]
DECAY_COLORS = {
    "β⁻": QColor("#3498db"), "β+": QColor("#e74c3c"), "EC": QColor("#e74c3c"),
    "α": QColor("#f1c40f"), "SF": QColor("#9b59b6"), "IT": QColor("#2ecc71"), "Stable": QColor("#2ecc71"),
    "p": QColor("#e67e22"), "n": QColor("#1abc9c")
}

# --- Utility Functions ---
def parse_hl(val, unit):
    try:
        v = float(val); u = unit.strip().lower()
        if u == 'y': return v * 3.154e7
        if u == 'd': return v * 86400
        if u == 'h': return v * 3600
        if u == 'm': return v * 60
        if u == 'ms': return v / 1000.0
        return v
    except: return None

def format_hl(sec):
    if not sec or sec <= 0: return "Stable"
    units = [(3.154e16, "Billion Years"), (3.154e13, "Million Years"), (3.154e7, "Years"), (86400, "Days"), (3600, "Hours"), (60, "Minutes"), (1, "Seconds"), (1e-3, "ms")]
    for div, lbl in units:
        if sec >= div: return f"{sec/div:.2f} {lbl}"
    return f"{sec:.2e} s"

def get_heat_color(v, min_v, max_v, is_log=False):
    if v is None or math.isnan(v): return QColor("#95a5a6")
    if is_log:
        if v <= 0: return QColor("#000033")
        v = math.log10(v); min_v = math.log10(min_v) if min_v > 0 else 0; max_v = math.log10(max_v) if max_v > 0 else 1
    r = 0.5 if max_v == min_v else (v - min_v) / (max_v - min_v)
    return QColor.fromHsv(int((1.0 - max(0.0, min(1.0, r))) * 240.0), 255, 255)

def get_numeric_cols(data, headers):
    cols = []
    for i, h in enumerate(headers):
        is_num = True; has_data = False
        for row in data[:100]:
            try:
                val = row[i].strip()
                if val: float(val); has_data = True
            except: is_num = False; break
        if is_num and has_data: cols.append(h)
    return cols

def get_decay_color(d):
    if not d: return DECAY_COLORS["Stable"]
    d = d.strip()
    return DECAY_COLORS.get(d, DECAY_COLORS.get(d[0], QColor("#7f8c8d")))

# --- Base Interactive Chart ---
class BaseChartView(QChartView):
    isotopeClicked = Signal(int)
    isotopeHovered = Signal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRubberBand(QChartView.RectangleRubberBand)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)
        
        self.chart = QChart(); self.chart.legend().hide(); self.setChart(self.chart)
        self._drag = None; self._is_drag = False
        self.point_map = {}
        
        self.hover_m = QScatterSeries(); self.hover_m.setColor(QColor(41, 128, 185, 100)); self.hover_m.setBorderColor(QColor(52, 152, 219)); self.hover_m.setMarkerSize(24)
        self.sel_m = QScatterSeries(); self.sel_m.setColor(QColor(231, 76, 60, 100)); self.sel_m.setBorderColor(QColor(192, 57, 43)); self.sel_m.setMarkerSize(28)
        self.chart.addSeries(self.hover_m); self.chart.addSeries(self.sel_m)

    def show_menu(self, pos):
        m = QMenu(self); m.addAction("Reset Zoom", self.chart.zoomReset); m.addAction("Save PNG", self.save_png); m.addAction("Toggle Grid", self.toggle_grid)
        m.exec_(self.viewport().mapToGlobal(pos))

    def save_png(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save", "chart.png", "PNG (*.png)")
        if f: self.grab().save(f, "PNG")

    def toggle_grid(self):
        for a in self.chart.axes(): a.setGridLineVisible(not a.isGridLineVisible())

    def wheelEvent(self, e):
        self.chart.zoom(1.15 if e.angleDelta().y() > 0 else 1/1.15); e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag = e.pos(); self._is_drag = False
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and self._drag:
            if (e.pos() - self._drag).manhattanLength() > 5:
                self._is_drag = True; d = e.pos() - self._drag; self.chart.scroll(-d.x(), d.y()); self._drag = e.pos()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and not self._is_drag: super().mousePressEvent(e)
        super().mouseReleaseEvent(e)

    def clear_chart(self):
        self.chart.removeAllSeries()
        for a in self.chart.axes(): self.chart.removeAxis(a)
        self.point_map.clear()
        self.hover_m = QScatterSeries(); self.hover_m.setColor(QColor(41, 128, 185, 100)); self.hover_m.setBorderColor(QColor(52, 152, 219)); self.hover_m.setMarkerSize(24)
        self.sel_m = QScatterSeries(); self.sel_m.setColor(QColor(231, 76, 60, 100)); self.sel_m.setBorderColor(QColor(192, 57, 43)); self.sel_m.setMarkerSize(28)
        self.chart.addSeries(self.hover_m); self.chart.addSeries(self.sel_m)

    def update_markers(self, row, data, headers):
        self.sel_m.removePoints(0, self.sel_m.count())
        if row != -1 and row < len(data):
            try:
                x, y = self.get_xy(row, data, headers)
                if x is not None: self.sel_m.append(x, y)
            except: pass

    def get_xy(self, row, data, headers): raise NotImplementedError

    def plot_data(self, data, headers, sel_row=-1):
        self.clear_chart()
        self._plot(data, headers, sel_row)
        for a in self.chart.axes(): self.hover_m.attachAxis(a); self.sel_m.attachAxis(a)
        self.update_markers(sel_row, data, headers)

    def _plot(self, data, headers, sel_row): pass

# --- Specific Chart Implementations ---

class NuclideChart(BaseChartView):
    def get_xy(self, r, d, h): return int(d[r][h.index('n')]), int(d[r][h.index('z')])
    def _plot(self, data, headers, sel_row):
        s_dict = {}; max_n = max_z = 0; dense = len(data) > 1000
        for r_idx, row in enumerate(data):
            try:
                z = int(row[headers.index('z')]); n = int(row[headers.index('n')]); dec = row[headers.index('decayMode')].strip()
                name = "Stable" if not dec else dec[0]; col = get_decay_color(dec)
                if name not in s_dict:
                    s = QScatterSeries(); s.setName(name); s.setColor(col); s.setMarkerSize(4 if dense else 8)
                    s.setBorderColor(col if not dense else Qt.transparent); s.setOpacity(0.6 if dense else 0.8)
                    s.hovered.connect(lambda pt, st, idx=r_idx: self.on_hov(idx, st)); s.clicked.connect(lambda pt, idx=r_idx: self.isotopeClicked.emit(idx))
                    s_dict[name] = s; self.chart.addSeries(s)
                s_dict[name].append(n, z); self.point_map[(n, z)] = r_idx
                max_n = max(max_n, n); max_z = max(max_z, z)
            except: continue
        
        for m in MAGIC_NUMBERS:
            if m <= max_n: l = QLineSeries(); l.append(m, 0); l.append(m, max_z+2); l.setColor(QColor("#bdc3c7")); self.chart.addSeries(l)
            if m <= max_z: l = QLineSeries(); l.append(0, m); l.append(max_n+2, m); l.setColor(QColor("#bdc3c7")); self.chart.addSeries(l)

        ax = QValueAxis(); ax.setTitleText("N"); ax.setRange(0, max_n+2); ax.setLabelFormat("%d")
        ay = QValueAxis(); ay.setTitleText("Z"); ay.setRange(0, max_z+2); ay.setLabelFormat("%d")
        self.chart.addAxis(ax, Qt.AlignBottom); self.chart.addAxis(ay, Qt.AlignLeft)
        for s in s_dict.values(): s.attachAxis(ax); s.attachAxis(ay)
        self.chart.legend().setVisible(True); self.chart.legend().setAlignment(Qt.AlignBottom)

    def on_hov(self, idx, st):
        if st:
            self.isotopeHovered.emit(idx, True)
            d = self.window().filtered_data; h = self.window().headers
            if idx < len(d): QToolTip.showText(QCursor.pos(), f"{d[idx][h.index('name')]}\nZ={d[idx][h.index('z')]}, N={d[idx][h.index('n')]}")
        else: self.isotopeHovered.emit(idx, False)

class GenericScatterChart(BaseChartView):
    def __init__(self, x_col, y_col, title, use_log_y=False, parent=None):
        super().__init__(parent); self.x_col = x_col; self.y_col = y_col; self.use_log = use_log_y; self.chart.setTitle(title)
    def get_xy(self, r, d, h):
        try: return float(d[r][h.index(self.x_col)]), float(d[r][h.index(self.y_col)])
        except: return None, None
    def _plot(self, data, headers, sel_row):
        s = QScatterSeries(); s.setColor(QColor("#9b59b6")); s.setMarkerSize(4); s.setOpacity(0.6); s.setBorderColor(Qt.transparent)
        s.hovered.connect(self.on_hov); s.clicked.connect(self.on_clk)
        xs, ys = [], []
        for r_idx, row in enumerate(data):
            x, y = self.get_xy(r_idx, row, headers)
            if x is not None and y is not None and not math.isnan(x) and not math.isnan(y):
                s.append(x, y); xs.append(x); ys.append(y); self.point_map[(x, y)] = r_idx
        self.chart.addSeries(s)
        if not xs: return
        min_x, max_x = min(xs), max(xs); min_y, max_y = min(ys), max(ys)
        px = (max_x - min_x) * 0.05 if max_x != min_x else 1; py = (max_y - min_y) * 0.05 if max_y != min_y else 1
        ax = QValueAxis(); ax.setTitleText(self.x_col); ax.setRange(min_x-px, max_x+px); self.chart.addAxis(ax, Qt.AlignBottom); s.attachAxis(ax)
        
        use_log = self.use_log or (min_y > 0 and max_y / min_y > 10000)
        if use_log and min_y > 0:
            ay = QLogValueAxis(); ay.setTitleText(f"{self.y_col} (Log)"); ay.setRange(min_y, max_y); ay.setLabelFormat("%.1e")
        else:
            ay = QValueAxis(); ay.setTitleText(self.y_col); ay.setRange(min_y-py, max_y+py); ay.setLabelFormat("%.2e")
        self.chart.addAxis(ay, Qt.AlignLeft); s.attachAxis(ay)

    def on_hov(self, pt, st):
        if st:
            d = self.window().filtered_data; h = self.window().headers
            closest = min(self.point_map.keys(), key=lambda k: (k[0]-pt.x())**2 + (k[1]-pt.y())**2)
            if abs(closest[0]-pt.x()) < 0.5 and abs(closest[1]-pt.y()) < abs(closest[1])*0.1:
                self.isotopeHovered.emit(self.point_map[closest], True)
                idx = self.point_map[closest]
                QToolTip.showText(QCursor.pos(), f"{d[idx][h.index('name')]}\n{self.x_col}={closest[0]:.2f}\n{self.y_col}={closest[1]:.2e}")
        else: self.isotopeHovered.emit(-1, False)

    def on_clk(self, pt):
        closest = min(self.point_map.keys(), key=lambda k: (k[0]-pt.x())**2 + (k[1]-pt.y())**2)
        if abs(closest[0]-pt.x()) < 0.5 and abs(closest[1]-pt.y()) < abs(closest[1])*0.1:
            self.isotopeClicked.emit(self.point_map[closest])

class HeatmapChart(BaseChartView):
    def __init__(self, parent=None): super().__init__(parent); self.metric = "halflife"; self.chart.setTitle("Heatmap")
    def get_xy(self, r, d, h): return int(d[r][h.index('n')]), int(d[r][h.index('z')])
    def set_metric(self, m): self.metric = m; self.plot_data(self.window().filtered_data, self.window().headers, self.window().table.currentRow())
    def _plot(self, data, headers, sel_row):
        vals, pts = [], []
        for r_idx, row in enumerate(data):
            try:
                n, z = int(row[headers.index('n')]), int(row[headers.index('z')])
                v = parse_hl(row[headers.index('halflife')], row[headers.index('halflifeUnit')]) if self.metric == "halflife" else float(row[headers.index(self.metric)])
                if v is not None: vals.append(v); pts.append((n, z, v, r_idx))
            except: continue
        if not vals: return
        min_v, max_v = min(vals), max(vals); is_log = min_v > 0 and max_v/min_v > 1000
        bins = [QScatterSeries() for _ in range(30)]
        for i, s in enumerate(bins):
            r = i/29; col = get_heat_color(min_v * (max_v/min_v)**r if is_log and min_v>0 else min_v + (max_v-min_v)*r, min_v, max_v, is_log)
            s.setColor(col); s.setMarkerSize(6); s.setBorderColor(Qt.transparent); s.setOpacity(0.9)
            s.hovered.connect(self.on_hov); s.clicked.connect(self.on_clk); self.chart.addSeries(s)
        for n, z, v, r_idx in pts:
            norm = (math.log10(v)-math.log10(max(min_v,1e-10)))/(math.log10(max_v)-math.log10(max(min_v,1e-10))) if is_log else (v-min_v)/(max_v-min_v) if max_v!=min_v else 0.5
            b = max(0, min(29, int(norm*29))); bins[b].append(n, z); self.point_map[(n, z)] = (r_idx, v)
        ax = QValueAxis(); ax.setTitleText("N"); ax.setRange(0, max(p[0] for p in pts)+2); ax.setLabelFormat("%d")
        ay = QValueAxis(); ay.setTitleText("Z"); ay.setRange(0, max(p[1] for p in pts)+2); ay.setLabelFormat("%d")
        self.chart.addAxis(ax, Qt.AlignBottom); self.chart.addAxis(ay, Qt.AlignLeft)
        for s in bins: s.attachAxis(ax); s.attachAxis(ay)
    def on_hov(self, pt, st):
        if st:
            k = (int(pt.x()), int(pt.y()))
            if k in self.point_map:
                r_idx, v = self.point_map[k]; self.isotopeHovered.emit(r_idx, True)
                d = self.window().filtered_data; h = self.window().headers
                QToolTip.showText(QCursor.pos(), f"{d[r_idx][h.index('name')]}\n{self.metric}: {format_hl(v) if self.metric=='halflife' else f'{v:.2f}'}")
        else: self.isotopeHovered.emit(-1, False)
    def on_clk(self, pt):
        k = (int(pt.x()), int(pt.y()))
        if k in self.point_map: self.isotopeClicked.emit(self.point_map[k][0])

class FissionYieldChart(BaseChartView):
    def __init__(self, cumulative=False, parent=None):
        super().__init__(parent); self.cum = cumulative; self.chart.setTitle(f"{'Cumulative' if cumulative else 'Independent'} Fission Yields")
    def get_xy(self, r, d, h):
        try: return int(d[r][h.index('z')])+int(d[r][h.index('n')]), float(d[r][h.index('cFY235U' if self.cum else 'FY235U')])
        except: return None, None
    def _plot(self, data, headers, sel_row):
        prefix = "cFY" if self.cum else "FY"
        cols = [h for h in headers if h.startswith(prefix) and "Unc" not in h]
        colors = [QColor("#e74c3c"), QColor("#3498db"), QColor("#2ecc71"), QColor("#f1c40f"), QColor("#9b59b6")]
        max_a = 0
        for i, c in enumerate(cols):
            s = QScatterSeries(); s.setName(c.replace(prefix, prefix+" ")); s.setColor(colors[i%5]); s.setMarkerSize(4); s.setOpacity(0.8)
            s.hovered.connect(self.on_hov); s.clicked.connect(self.on_clk)
            for r_idx, row in enumerate(data):
                try:
                    a = int(row[headers.index('z')])+int(row[headers.index('n')]); v = float(row[headers.index(c)])
                    if v > 0: s.append(a, v); max_a = max(max_a, a)
                except: continue
            self.chart.addSeries(s)
        if max_a == 0: return
        ax = QValueAxis(); ax.setTitleText("A"); ax.setRange(0, max_a+2); ax.setLabelFormat("%d")
        ay = QLogValueAxis(); ay.setTitleText("Yield (%)"); ay.setRange(1e-6, 100); ay.setLabelFormat("%.1e")
        self.chart.addAxis(ax, Qt.AlignBottom); self.chart.addAxis(ay, Qt.AlignLeft)
        for s in self.chart.series():
            if s.type() == QScatterSeries.Type: s.attachAxis(ax); s.attachAxis(ay)
        self.chart.legend().setVisible(True); self.chart.legend().setAlignment(Qt.AlignBottom)
    def on_hov(self, pt, st):
        if st:
            d = self.window().filtered_data; h = self.window().headers; p = "cFY" if self.cum else "FY"
            for r_idx, row in enumerate(d):
                try:
                    a = int(row[h.index('z')])+int(row[h.index('n')])
                    if abs(a-pt.x()) < 0.5:
                        for col in h:
                            if col.startswith(p) and "Unc" not in col:
                                v = float(row[h.index(col)])
                                if abs(v-pt.y()) < v*0.2: self.isotopeHovered.emit(r_idx, True); QToolTip.showText(QCursor.pos(), f"{row[h.index('name')]} (A={a})\n{col}: {v:.2e}%"); return
                except: continue
        else: self.isotopeHovered.emit(-1, False)
    def on_clk(self, pt):
        d = self.window().filtered_data; h = self.window().headers
        for r_idx, row in enumerate(d):
            try:
                if abs((int(row[h.index('z')])+int(row[h.index('n')]))-pt.x()) < 0.5: self.isotopeClicked.emit(r_idx); return
            except: continue

class LevelSchemeChart(QChartView):
    def __init__(self, p=None): super().__init__(p); self.setRenderHint(QPainter.Antialiasing); self.chart = QChart(); self.chart.setTitle("Level Scheme"); self.setChart(self.chart)
    def plot_data(self, data, headers, sel_row=-1):
        self.chart.removeAllSeries()
        for a in self.chart.axes(): self.chart.removeAxis(a)
        if sel_row == -1 or sel_row >= len(data): return
        z = data[sel_row][headers.index('z')]; n = data[sel_row][headers.index('n')]; name = data[sel_row][headers.index('name')].rstrip('m0123456789')
        states = []
        for row in data:
            try:
                if int(row[headers.index('z')]) == int(z) and int(row[headers.index('n')]) == int(n): states.append((float(row[headers.index('levelEnergy(MeV)')]), row))
            except: continue
        if not states: return
        states.sort(key=lambda x: x[0]); max_e = max(s[0] for s in states) + 0.5
        for e, row in states:
            s = QLineSeries(); s.setColor(get_decay_color(row[headers.index('decayMode')])); s.setPenWidth(4); s.append(0, e); s.append(1, e)
            s.setName(f"{row[headers.index('name')]} ({row[headers.index('spinAndParity')]}) {row[headers.index('halflife')]} {row[headers.index('halflifeUnit')]}")
            s.hovered.connect(lambda st, ser=s: QToolTip.showText(QCursor.pos(), ser.name()) if st else None)
            self.chart.addSeries(s)
        ax = QValueAxis(); ax.setRange(-0.5, 1.5); ax.setVisible(False)
        ay = QValueAxis(); ay.setTitleText("E* (MeV)"); ay.setRange(-0.2, max_e)
        self.chart.addAxis(ax, Qt.AlignBottom); self.chart.addAxis(ay, Qt.AlignLeft)
        for s in self.chart.series(): s.attachAxis(ax); s.attachAxis(ay)
        self.chart.setTitle(f"Levels for {name}-{int(z)+int(n)}")

class IsotopeQBarChart(QChartView):
    def __init__(self, p=None): super().__init__(p); self.setRenderHint(QPainter.Antialiasing); self.chart = QChart(); self.chart.setTitle("Isotope Q-Values"); self.setChart(self.chart)
    def plot_data(self, data, headers, sel_row=-1):
        self.chart.removeAllSeries()
        for a in self.chart.axes(): self.chart.removeAxis(a)
        if sel_row == -1 or sel_row >= len(data): return
        row = data[sel_row]; name = row[headers.index('name')]; qs = {}
        for m in ["betaMinus", "electronCapture", "positronEmission", "alpha", "doubleBetaMinus", "betaMinusOneNeutronEmission"]:
            try:
                v = float(row[headers.index(m)])
                if v != 0: qs[m] = v
            except: pass
        if not qs: self.chart.setTitle(f"No Q-Values for {name}"); return
        s = QBarSeries(); bs = QBarSet("Q (keV)"); ax = QBarCategoryAxis()
        for m, v in qs.items(): bs.append(v); ax.append(m)
        s.append(bs); self.chart.addSeries(s); self.chart.addAxis(ax, Qt.AlignBottom); s.attachAxis(ax)
        ay = QValueAxis(); ay.setTitleText("keV"); ay.setRange(0, max(qs.values())*1.1); self.chart.addAxis(ay, Qt.AlignLeft); s.attachAxis(ay)
        self.chart.setTitle(f"Decay Q-Values for {name}")

class DecayPieChart(QChartView):
    def __init__(self, p=None): super().__init__(p); self.setRenderHint(QPainter.Antialiasing); self.chart = QChart(); self.chart.setTitle("Decay Distribution"); self.setChart(self.chart)
    def plot_data(self, data, headers, sel_row=-1):
        self.chart.removeAllSeries()
        for a in self.chart.axes(): self.chart.removeAxis(a)
        counts = {}
        for row in data:
            d = row[headers.index('decayMode')].strip(); d = "Stable" if not d else d[0]; counts[d] = counts.get(d, 0) + 1
        s = QPieSeries()
        for d, c in counts.items():
            sl = s.append(d, c); sl.setLabelVisible(True); sl.setLabel(f"{d} ({c})")
            sl.clicked.connect(lambda x=QColor.randomColor(): None) # Just to allow hover
        self.chart.addSeries(s); self.chart.legend().setVisible(True); self.chart.legend().setAlignment(Qt.AlignRight)

class HistoChart(QChartView):
    def __init__(self, p=None): super().__init__(p); self.setRenderHint(QPainter.Antialiasing); self.chart = QChart(); self.chart.setTitle("Half-life Distribution"); self.setChart(self.chart)
    def plot_data(self, data, headers, sel_row=-1):
        self.chart.removeAllSeries()
        for a in self.chart.axes(): self.chart.removeAxis(a)
        bins = [-12, -9, -6, -3, 0, 3, 6, 9, 12]; counts = [0]*(len(bins)-1)
        for row in data:
            hl = parse_hl(row[headers.index('halflife')], row[headers.index('halflifeUnit')])
            if hl and hl > 0:
                lh = math.log10(hl)
                for i in range(len(bins)-1):
                    if bins[i] <= lh < bins[i+1]: counts[i] += 1; break
        s = QBarSeries(); bs = QBarSet("Count")
        for c in counts: bs.append(c)
        s.append(bs); self.chart.addSeries(s)
        ax = QBarCategoryAxis(); ax.append(["1ps", "1ns", "1µs", "1ms", "1s", "1ks", "1Ms", "1Gs", "1Ts"]); self.chart.addAxis(ax, Qt.AlignBottom); s.attachAxis(ax)
        ay = QValueAxis(); ay.setTitleText("Count"); ay.setRange(0, max(counts)*1.1 if counts else 10); self.chart.addAxis(ay, Qt.AlignLeft); s.attachAxis(ay)

class StatsTab(QWidget):
    def __init__(self, p=None):
        super().__init__(p); self.layout = QGridLayout(self); self.layout.setContentsMargins(20,20,20,20); self.labels = {}
        metrics = ["Total States", "Ground States", "Isomers", "Most Common Decay", "Avg BE/A (keV)", "Highest BE/A", "Longest Half-life"]
        for i, m in enumerate(metrics):
            t = QLabel(m); t.setStyleSheet("font-weight: bold; font-size: 14px; color: #34495e;")
            v = QLabel("N/A"); v.setStyleSheet("font-size: 16px; color: #2c3e50; padding: 5px;")
            self.layout.addWidget(t, i, 0); self.layout.addWidget(v, i, 1); self.labels[m] = v
        self.layout.setColumnStretch(1, 1)
    def update_stats(self, data, headers):
        gs = sum(1 for r in data if r[headers.index('levelEnergy(MeV)')] == "0")
        self.labels["Total States"].setText(str(len(data)))
        self.labels["Ground States"].setText(str(gs))
        self.labels["Isomers"].setText(str(len(data) - gs))
        if not data: return
        decs = [r[headers.index('decayMode')].strip() if r[headers.index('decayMode')].strip() else "Stable" for r in data]
        mc = max(set(decs), key=decs.count); self.labels["Most Common Decay"].setText(f"{mc} ({decs.count(mc)})")
        bes = [(float(r[headers.index('bindingEnergy')])/(int(r[headers.index('z')])+int(r[headers.index('n')])), r[headers.index('name')]) for r in data if float(r[headers.index('bindingEnergy')]) > 0 and int(r[headers.index('z')])+int(r[headers.index('n')]) > 0]
        if bes: self.labels["Avg BE/A (keV)"].setText(f"{sum(b[0] for b in bes)/len(bes):.2f}"); self.labels["Highest BE/A"].setText(f"{max(bes)[1]} ({max(bes)[0]:.2f})")
        hls = [(parse_hl(r[headers.index('halflife')], r[headers.index('halflifeUnit')]), r[headers.index('name')]) for r in data if parse_hl(r[headers.index('halflife')], r[headers.index('halflifeUnit')])]
        if hls: self.labels["Longest Half-life"].setText(f"{max(hls)[1]} ({format_hl(max(hls)[0])})")

# --- Main Application ---

class IsotopeViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ultimate Nuclear Physics Viewer")
        self.resize(1400, 900)
        
        self.headers = HEADERS.split(',')
        self.full_data = [row.split(',') for row in DEFAULT_DATA]
        self.normalize_data(self.full_data)
        self.filtered_data = self.full_data[:]
        self.numeric_cols = get_numeric_cols(self.full_data, self.headers)
        self.dark_mode = False
        self.active_charts = [] # Tracks charts to update on filter change
        
        self.init_ui()
        self.populate_table(self.filtered_data)
        self.update_active_charts()

    def normalize_data(self, data):
        for row in data:
            if len(row) < len(self.headers): row.extend([''] * (len(self.headers) - len(row)))

    def init_ui(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(QAction("&Load CSV...", self, triggered=self.load_csv))
        file_menu.addAction(QAction("Export &Filtered CSV...", self, triggered=self.export_csv))
        view_menu = menubar.addMenu("&View")
        self.theme_action = QAction("Toggle Dark Mode", self, checkable=True); self.theme_action.triggered.connect(self.toggle_theme); view_menu.addAction(self.theme_action)

        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central); main_layout.setContentsMargins(5,5,5,5)

        # Filter Bar
        s_layout = QHBoxLayout()
        s_layout.addWidget(QLabel("Search:"))
        self.search = QLineEdit(); self.search.setPlaceholderText("name:Li, decay:α, z:3, a:8, or just '8'")
        self.search.textChanged.connect(self.filter_data); s_layout.addWidget(self.search)
        self.decay_combo = QComboBox(); self.decay_combo.addItems(["All", "β⁻", "β+", "EC", "α", "IT", "Stable"])
        self.decay_combo.currentTextChanged.connect(lambda t: self.search.setText(f"decay:{t}" if t != "All" else "")); s_layout.addWidget(self.decay_combo)
        self.gs_check = QCheckBox("Ground States Only"); self.gs_check.stateChanged.connect(self.filter_data); s_layout.addWidget(self.gs_check)
        s_layout.addWidget(QLabel("Z:")); self.z_min = QSpinBox(); self.z_min.setRange(0,200); self.z_max = QSpinBox(); self.z_max.setRange(0,200); self.z_max.setValue(200)
        s_layout.addWidget(self.z_min); s_layout.addWidget(self.z_max)
        s_layout.addWidget(QLabel("N:")); self.n_min = QSpinBox(); self.n_min.setRange(0,300); self.n_max = QSpinBox(); self.n_max.setRange(0,300); self.n_max.setValue(300)
        s_layout.addWidget(self.n_min); s_layout.addWidget(self.n_max)
        btn = QPushButton("Clear"); btn.clicked.connect(self.clear_filters); s_layout.addWidget(btn)
        main_layout.addLayout(s_layout)

        # Main Splitter
        h_split = QSplitter(Qt.Horizontal)
        
        # Chart Tabs (Categorized)
        self.chart_tabs = QTabWidget()
        self.chart_tabs.currentChanged.connect(self.update_active_charts)

        # 1. Maps
        self.nuclide_chart = NuclideChart()
        self.heatmap = HeatmapChart()
        hm_widget = QWidget(); hm_layout = QVBoxLayout(hm_widget); hm_layout.setContentsMargins(0,0,0,0)
        hm_layout.addWidget(self.heatmap); m_layout = QHBoxLayout(); m_layout.addWidget(QLabel("Metric:"))
        self.metric_combo = QComboBox(); self.metric_combo.addItems(["halflife"] + [c for c in self.numeric_cols if c not in ["halflife", "z", "n"]])
        self.metric_combo.currentTextChanged.connect(self.heatmap.set_metric); m_layout.addWidget(self.metric_combo); m_layout.addStretch(); hm_layout.addLayout(m_layout)
        
        self.be_surface = GenericScatterChart("n", "z", "BE Surface (Color Proxy)") # Simplified for performance
        
        maps_tab = QTabWidget()
        maps_tab.addTab(self.nuclide_chart, "Nuclides (N vs Z)")
        maps_tab.addTab(hm_widget, "Heatmap")
        maps_tab.addTab(self.be_surface, "BE Surface")
        maps_tab.currentChanged.connect(self.update_active_charts)
        self.chart_tabs.addTab(maps_tab, "🗺️ Nuclide Maps")

        # 2. Decay & Q-Values
        decay_tab = QTabWidget()
        self.q_landscape = GenericScatterChart("betaMinus", "alpha", "Q-Value Landscape (Alpha vs Beta-)")
        self.alpha_q = GenericScatterChart("n", "alpha", "Alpha Q-Value vs N")
        self.beta_q = GenericScatterChart("n", "betaMinus", "Beta Minus Q-Value vs N")
        self.ec_beta = GenericScatterChart("electronCapture", "positronEmission", "EC vs Beta+ Q-Values")
        self.q_bar = IsotopeQValueBarChart()
        decay_tab.addTab(self.q_landscape, "Q-Value Landscape")
        decay_tab.addTab(self.alpha_q, "Alpha Q vs N")
        decay_tab.addTab(self.beta_q, "Beta- Q vs N")
        decay_tab.addTab(self.ec_beta, "EC vs Beta+")
        decay_tab.addTab(self.q_bar, "Selected Q-Values")
        decay_tab.currentChanged.connect(self.update_active_charts)
        self.chart_tabs.addTab(decay_tab, "☢️ Decay & Q-Values")

        # 3. Structure
        struct_tab = QTabWidget()
        self.level_scheme = LevelSchemeChart()
        self.first_2p = GenericScatterChart("n", "firstTwoPlusEnergy", "First 2+ Energy vs N")
        self.r42 = GenericScatterChart("n", "firstFourPlusOverFirstTwoPlusEnergy", "R4/2 Ratio vs N")
        self.delta_a = GenericScatterChart("n", "deltaAlpha", "Delta Alpha vs N")
        self.uncertainty = GenericScatterChart("massExcess(keV)", "massExcessUncertainty", "Mass Excess Uncertainty", use_log_y=True)
        struct_tab.addTab(self.level_scheme, "Level Scheme")
        struct_tab.addTab(self.first_2p, "First 2+ Energy")
        struct_tab.addTab(self.r42, "R4/2 Ratio")
        struct_tab.addTab(self.delta_a, "Delta Alpha")
        struct_tab.addTab(self.uncertainty, "Experimental Uncertainty")
        struct_tab.currentChanged.connect(self.update_active_charts)
        self.chart_tabs.addTab(struct_tab, "⚛️ Nuclear Structure")

        # 4. Fission
        fis_tab = QTabWidget()
        self.fy_ind = FissionYieldChart(cumulative=False)
        self.fy_cum = FissionYieldChart(cumulative=True)
        self.sn = GenericScatterChart("n", "neutronSeparationEnergy", "Sn vs N")
        self.sp = GenericScatterChart("z", "protonSeparationEnergy", "Sp vs Z")
        fis_tab.addTab(self.fy_ind, "Independent FY")
        fis_tab.addTab(self.fy_cum, "Cumulative FY")
        fis_tab.addTab(self.sn, "Neutron Sep. E")
        fis_tab.addTab(self.sp, "Proton Sep. E")
        fis_tab.currentChanged.connect(self.update_active_charts)
        self.chart_tabs.addTab(fis_tab, "📉 Fission & Reactors")

        # 5. Stats & Distributions
        stats_tab = QTabWidget()
        self.pie = DecayPieChart()
        self.histo = HistoChart()
        self.stats = StatsTab()
        stats_tab.addTab(self.pie, "Decay Pie")
        stats_tab.addTab(self.histo, "Half-life Hist")
        stats_tab.addTab(self.stats, "Statistics Dashboard")
        stats_tab.currentChanged.connect(self.update_active_charts)
        self.chart_tabs.addTab(stats_tab, "📊 Stats & Distributions")

        # 6. Custom
        custom_tab = QTabWidget()
        self.custom = GenericScatterChart("z", "bindingEnergy", "Custom X-Y Plot")
        c_widget = QWidget(); c_layout = QVBoxLayout(c_widget); c_layout.setContentsMargins(0,0,0,0); c_layout.addWidget(self.custom)
        ax_layout = QHBoxLayout(); ax_layout.addWidget(QLabel("X:")); self.x_combo = QComboBox(); self.x_combo.addItems(self.numeric_cols); ax_layout.addWidget(self.x_combo)
        ax_layout.addWidget(QLabel("Y:")); self.y_combo = QComboBox(); self.y_combo.addItems(self.numeric_cols); self.y_combo.setCurrentText("bindingEnergy"); ax_layout.addWidget(self.y_combo)
        plot_btn = QPushButton("Plot"); plot_btn.clicked.connect(lambda: self.custom.__init__(self.x_combo.currentText(), self.y_combo.currentText(), f"{self.y_combo.currentText()} vs {self.x_combo.currentText()}") or self.update_active_charts())
        ax_layout.addWidget(plot_btn); ax_layout.addStretch(); c_layout.addLayout(ax_layout)
        custom_tab.addTab(c_widget, "Custom Plot")
        custom_tab.currentChanged.connect(self.update_active_charts)
        self.chart_tabs.addTab(custom_tab, "⚙️ Custom Tools")
        
        h_split.addWidget(self.chart_tabs)

        # Right Side
        v_split = QSplitter(Qt.Vertical)
        self.table = QTableWidget(); self.table.setColumnCount(len(self.headers)); self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self.update_details_panel)
        for c in HIDDEN_COLS:
            if c in self.headers: self.table.setColumnHidden(self.headers.index(c), True)

        self.details = QTextBrowser(); self.details.setStyleSheet("background-color: #f9f9f9; font-size: 14px;")
        v_split.addWidget(self.table); v_split.addWidget(self.details)
        h_split.addWidget(v_split); h_split.setSizes([600, 800])
        main_layout.addWidget(h_split)
        self.setStatusBar(QStatusBar())

    def toggle_theme(self):
        self.dark_mode = self.theme_action.isChecked()
        app.setStyleSheet(DARK_STYLESHEET if self.dark_mode else LIGHT_STYLESHEET)
        for i in range(self.chart_tabs.count()):
            tab = self.chart_tabs.widget(i)
            if isinstance(tab, QTabWidget):
                for j in range(tab.count()):
                    chart = tab.widget(j)
                    if isinstance(chart, QChartView): chart.chart().setTheme(QChart.ChartThemeDark if self.dark_mode else QChart.ChartThemeLight)
        self.update_active_charts()

    def clear_filters(self):
        self.search.clear(); self.decay_combo.setCurrentText("All"); self.gs_check.setChecked(False)
        self.z_min.setValue(0); self.z_max.setValue(200); self.n_min.setValue(0); self.n_max.setValue(300)

    def populate_table(self, data):
        self.table.setSortingEnabled(False); self.table.setRowCount(0)
        for r, row in enumerate(data):
            self.table.insertRow(r)
            for c, val in enumerate(row):
                item = QTableWidgetItem(val.strip())
                try: float(val.strip()); item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                except: pass
                if self.headers[c] == 'decayMode':
                    item.setForeground(get_decay_color(val.strip())); f = QFont(); f.setBold(True); item.setFont(f)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True); self.table.resizeColumnsToContents()
        if self.table.rowCount() > 0: self.table.selectRow(0)
        else: self.details.clear()

    def filter_data(self):
        q = self.search.text().lower().strip(); gs = self.gs_check.isChecked()
        z_min, z_max = self.z_min.value(), self.z_max.value(); n_min, n_max = self.n_min.value(), self.n_max.value()
        self.filtered_data = []; s_type = None; s_val = q
        if ":" in q: p = q.split(":", 1); s_type = p[0].strip(); s_val = p[1].strip()
        for row in self.full_data:
            try: z = int(row[self.headers.index('z')]); n = int(row[self.headers.index('n')]); a = z+n
            except: continue
            if not (z_min <= z <= z_max and n_min <= n <= n_max): continue
            if gs:
                try:
                    if float(row[self.headers.index('levelEnergy(MeV)')]) != 0.0: continue
                except: pass
            if not q: self.filtered_data.append(row); continue
            zs, ns, as_ = str(z).lower(), str(n).lower(), str(a).lower()
            name = row[self.headers.index('name')].lower(); dec = row[self.headers.index('decayMode')].lower()
            m = False
            if s_type == "name": m = s_val in name
            elif s_type == "decay": m = s_val in dec
            elif s_type == "z": m = s_val == zs
            elif s_type == "n": m = s_val == ns
            elif s_type == "a": m = s_val == as_
            else: m = s_val in zs or s_val in ns or s_val in name or s_val in dec or s_val in as_
            if m: self.filtered_data.append(row)
        self.populate_table(self.filtered_data)
        self.update_active_charts()
        self.statusBar().showMessage(f"Showing {len(self.filtered_data)} of {len(self.full_data)} states")

    def get_active_charts(self):
        charts = []
        main_tab = self.chart_tabs.currentWidget()
        if isinstance(main_tab, QTabView): # Wait, QTabWidget
            pass
        if isinstance(main_tab, QTabWidget):
            sub_tab = main_tab.currentWidget()
            if isinstance(sub_tab, QChartView): charts.append(sub_tab)
            elif isinstance(sub_tab, QWidget):
                # Handle custom widgets inside tabs (like Heatmap layout)
                for child in sub_tab.children():
                    if isinstance(child, QChartView): charts.append(child)
        return charts

    def update_active_charts(self):
        sel_row = self.table.currentRow()
        charts = self.get_active_charts()
        for c in charts:
            if hasattr(c, 'plot_data'): c.plot_data(self.filtered_data, self.headers, sel_row)

    def get_val(self, r, col):
        try: item = self.table.item(r, self.headers.index(col)); return item.text().strip() if item else ""
        except: return ""

    def update_details_panel(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows: return
        r = rows[0].row()
        if r == -1: return
        self.update_active_charts()
        name = self.get_val(r, "name"); z = self.get_val(r, "z"); n = self.get_val(r, "n")
        hl = self.get_val(r, "halflife"); hu = self.get_val(r, "halflifeUnit")
        hls = parse_hl(hl, hu); hld = format_hl(hls) if hls else "N/A"
        html = f"<h2>{name}</h2><b>Z:</b> {z} | <b>N:</b> {n} | <b>A:</b> {int(z)+int(n) if z.isdigit() and n.isdigit() else 'N/A'}<br>"
        html += f"<b>Half-Life:</b> {hl} {hu} (~{hld})<br><b>Decay:</b> {self.get_val(r, 'decayMode')}<br>"
        html += f"<b>Binding E:</b> {self.get_val(r, 'bindingEnergy')} keV<br><b>Mass Excess:</b> {self.get_val(r, 'massExcess(keV)')} keV"
        self.details.setHtml(html)

    def load_csv(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV (*.csv)")
        if f:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    reader = csv.reader(file); lh = next(reader); ld = list(reader)
                self.headers = lh; self.normalize_data(ld); self.full_data = ld; self.filtered_data = self.full_data[:]
                self.numeric_cols = get_numeric_cols(self.full_data, self.headers)
                self.metric_combo.clear(); self.metric_combo.addItems(["halflife"] + [c for c in self.numeric_cols if c not in ["halflife", "z", "n"]])
                self.x_combo.clear(); self.x_combo.addItems(self.numeric_cols); self.y_combo.clear(); self.y_combo.addItems(self.numeric_cols)
                self.table.setColumnCount(len(self.headers)); self.table.setHorizontalHeaderLabels(self.headers)
                self.populate_table(self.filtered_data); self.update_active_charts()
                QMessageBox.information(self, "Success", f"Loaded {len(ld)} records.")
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def export_csv(self):
        if not self.filtered_data: return
        f, _ = QFileDialog.getSaveFileName(self, "Save CSV", "filtered.csv", "CSV (*.csv)")
        if f:
            try:
                with open(f, 'w', newline='', encoding='utf-8') as file:
                    w = csv.writer(file); w.writerow(self.headers); w.writerows(self.filtered_data)
                QMessageBox.information(self, "Success", "Exported.")
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

LIGHT_STYLESHEET = """
    QMainWindow { background-color: #ecf0f1; }
    QHeaderView::section { background-color: #34495e; color: white; padding: 4px; border: 1px solid #2c3e50; font-weight: bold; }
    QTableWidget { gridline-color: #bdc3c7; background-color: white; alternate-background-color: #f4f6f7; }
    QTableWidget::item:selected { background-color: #3498db; color: white; }
    QLineEdit, QComboBox, QSpinBox { padding: 4px; border: 1px solid #bdc3c7; border-radius: 3px; background-color: white; }
    QPushButton { padding: 5px 15px; background-color: #e74c3c; color: white; border: none; border-radius: 3px; font-weight: bold; }
    QPushButton:hover { background-color: #c0392b; }
    QTabWidget::pane { border: 1px solid #bdc3c7; }
    QTabBar::tab { background-color: #ecf0f1; padding: 8px 12px; border: 1px solid #bdc3c7; border-bottom: none; }
    QTabBar::tab:selected { background-color: white; font-weight: bold; }
    QStatusBar { background-color: #34495e; color: white; }
"""

DARK_STYLESHEET = """
    QMainWindow { background-color: #1a252f; }
    QHeaderView::section { background-color: #2c3e50; color: #ecf0f1; padding: 4px; border: 1px solid #34495e; font-weight: bold; }
    QTableWidget { gridline-color: #34495e; background-color: #2c3e50; alternate-background-color: #243441; color: #ecf0f1; }
    QTableWidget::item:selected { background-color: #2980b9; color: white; }
    QLineEdit, QComboBox, QSpinBox { padding: 4px; border: 1px solid #34495e; border-radius: 3px; background-color: #243441; color: #ecf0f1; }
    QPushButton { padding: 5px 15px; background-color: #c0392b; color: white; border: none; border-radius: 3px; font-weight: bold; }
    QPushButton:hover { background-color: #e74c3c; }
    QTabWidget::pane { border: 1px solid #34495e; }
    QTabBar::tab { background-color: #243441; color: #bdc3c7; padding: 8px 12px; border: 1px solid #34495e; border-bottom: none; }
    QTabBar::tab:selected { background-color: #2c3e50; color: white; font-weight: bold; }
    QStatusBar { background-color: #2c3e50; color: #ecf0f1; }
    QLabel { color: #ecf0f1; }
    QCheckBox { color: #ecf0f1; }
    QToolTip { background-color: #2c3e50; color: white; border: 1px solid black; }
"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(LIGHT_STYLESHEET)
    window = IsotopeViewer()
    window.show()
    sys.exit(app.exec())