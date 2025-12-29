"""
Sistema de Consulta CUFE DIAN - v4.5.0
Diseño Limpio y Moderno
© C. Guerrero | A.S. Contadores & Asesores SAS
"""

import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from PIL import Image, ImageTk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import cargar_settings
    from core.orquestador import ejecutar_sistema
    from core.validador import cargar_cufes
    from core.excel_generator import generar_excel_final
    MODULOS_DISPONIBLES = True
except ImportError as e:
    print(f"Aviso: Módulos no disponibles ({e})")
    MODULOS_DISPONIBLES = False


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

APP = {
    'title': 'CUFE DIAN',
    'version': '4.5.0',
    'company': 'A.S. Contadores & Asesores SAS',
    'location': '',
    'dev': '© C. Guerrero',
    'width': 920,
    'height': 680,
    'max_nav': 10,
}

# Colores
C = {
    'primary': '#1B5E20',
    'primary_hover': '#2E7D32',
    'bg': '#F5F7F9',
    'card': '#FFFFFF',
    'text': '#2D3748',
    'text_soft': '#718096',
    'text_muted': '#A0AEC0',
    'success': '#22C55E',
    'warning': '#F59E0B',
    'error': '#EF4444',
    'info': '#3B82F6',
    'border': '#E2E8F0',
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title(APP['title'])
        self.geometry(f"{APP['width']}x{APP['height']}")
        self.minsize(APP['width'], APP['height'])
        self.resizable(False, False)
        self.configure(bg=C['bg'])
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Estado
        self.processing = False
        self.stop_requested = False
        self.archivo_var = tk.StringVar(value="")
        self.carpeta_var = tk.StringVar(value=os.path.expanduser("~"))
        self.cufes_validos = []
        self.cufes_invalidos = []
        self.duplicados = 0
        self.total = 0
        self.resultado = None
        self.excel_path = None
        self.log_queue = queue.Queue()
        
        # Progreso
        self.progreso_visual = 0.0
        self.progreso_objetivo = 0.0
        self.anim_activa = False
        
        self.setup_icon()
        self.center()
        self.build_ui()
        self.process_logs()
    
    def resource_path(self, rel):
        try:
            return os.path.join(sys._MEIPASS, rel)
        except:
            return os.path.join(os.path.dirname(__file__), rel)
    
    def center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - APP['width']) // 2
        y = (self.winfo_screenheight() - APP['height']) // 2 - 40
        self.geometry(f"{APP['width']}x{APP['height']}+{x}+{y}")
    
    def setup_icon(self):
        try:
            import platform
            if platform.system() == "Windows":
                for p in [self.resource_path("assets/dian.ico"), "dian.ico"]:
                    if os.path.exists(p):
                        self.iconbitmap(default=p)
                        return
            for p in [self.resource_path("assets/logo.png"), "logo.png"]:
                if os.path.exists(p):
                    img = Image.open(p)
                    icons = [ImageTk.PhotoImage(img.resize((s,s), Image.Resampling.LANCZOS)) for s in [48,32,16]]
                    self.iconphoto(True, *icons)
                    self._icons = icons
                    return
        except: pass
    
    def load_logo(self, max_w=280, max_h=70):
        for p in [self.resource_path("assets/logo.png"), "logo.png"]:
            if os.path.exists(p):
                try:
                    img = Image.open(p)
                    ratio = min(max_w/img.width, max_h/img.height)
                    if ratio < 1:
                        img = img.resize((int(img.width*ratio), int(img.height*ratio)), Image.Resampling.LANCZOS)
                    return ImageTk.PhotoImage(img)
                except: pass
        return None
    
    def build_ui(self):
        # === HEADER con logo centrado ===
        header = tk.Frame(self, bg=C['card'], height=90)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        # Logo centrado
        logo = self.load_logo(280, 65)
        if logo:
            self._logo = logo
            tk.Label(header, image=logo, bg=C['card']).pack(expand=True, pady=12)
        else:
            tk.Label(header, text="A.S. Contadores & Asesores", font=('Segoe UI', 18, 'bold'),
                    fg=C['primary'], bg=C['card']).pack(expand=True, pady=20)
        
        # Línea verde
        tk.Frame(self, bg=C['primary'], height=4).pack(fill=tk.X)
        
        # === CONTENIDO PRINCIPAL ===
        main = tk.Frame(self, bg=C['bg'])
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # --- Barra de archivos compacta ---
        file_bar = tk.Frame(main, bg=C['card'], highlightbackground=C['border'], highlightthickness=1)
        file_bar.pack(fill=tk.X, pady=(0, 12))
        
        inner = tk.Frame(file_bar, bg=C['card'])
        inner.pack(fill=tk.X, padx=12, pady=10)
        
        # Archivo
        tk.Label(inner, text="📄", font=('Segoe UI', 11), bg=C['card']).pack(side=tk.LEFT)
        self.lbl_archivo = tk.Label(inner, text="Seleccionar archivo...", font=('Segoe UI', 9),
                                   fg=C['text_soft'], bg=C['card'], anchor='w')
        self.lbl_archivo.pack(side=tk.LEFT, padx=(5, 15), fill=tk.X, expand=True)
        
        self.btn_archivo = tk.Button(inner, text="Examinar", font=('Segoe UI', 9, 'bold'),
                                    bg=C['primary'], fg='white', relief='flat', cursor='hand2',
                                    command=self.seleccionar_archivo, padx=12, pady=4,
                                    activebackground=C['primary_hover'])
        self.btn_archivo.pack(side=tk.LEFT, padx=(0, 15))
        
        # Separador
        tk.Frame(inner, bg=C['border'], width=1).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Destino
        tk.Label(inner, text="📁", font=('Segoe UI', 11), bg=C['card']).pack(side=tk.LEFT)
        self.lbl_destino = tk.Label(inner, text="Carpeta de salida", font=('Segoe UI', 9),
                                   fg=C['text_soft'], bg=C['card'])
        self.lbl_destino.pack(side=tk.LEFT, padx=(5, 10))
        
        self.btn_destino = tk.Button(inner, text="Cambiar", font=('Segoe UI', 9),
                                    bg=C['border'], fg=C['text'], relief='flat', cursor='hand2',
                                    command=self.seleccionar_carpeta, padx=10, pady=4)
        self.btn_destino.pack(side=tk.LEFT)
        
        # --- Validación y botones ---
        ctrl_frame = tk.Frame(main, bg=C['bg'])
        ctrl_frame.pack(fill=tk.X, pady=(0, 12))
        
        # Indicadores izquierda
        ind = tk.Frame(ctrl_frame, bg=C['bg'])
        ind.pack(side=tk.LEFT)
        
        self.lbl_valid = tk.Label(ind, text="✓ 0", font=('Segoe UI', 10, 'bold'),
                                 fg=C['success'], bg=C['bg'])
        self.lbl_valid.pack(side=tk.LEFT, padx=(0, 12))
        
        self.lbl_invalid = tk.Label(ind, text="✗ 0", font=('Segoe UI', 10, 'bold'),
                                   fg=C['error'], bg=C['bg'])
        self.lbl_invalid.pack(side=tk.LEFT, padx=(0, 12))
        
        self.lbl_dup = tk.Label(ind, text="◐ 0", font=('Segoe UI', 10),
                               fg=C['warning'], bg=C['bg'])
        self.lbl_dup.pack(side=tk.LEFT, padx=(0, 20))
        
        self.lbl_total = tk.Label(ind, text="Total: 0", font=('Segoe UI', 10, 'bold'),
                                 fg=C['primary'], bg=C['bg'])
        self.lbl_total.pack(side=tk.LEFT)
        
        # Botones derecha
        btns = tk.Frame(ctrl_frame, bg=C['bg'])
        btns.pack(side=tk.RIGHT)
        
        self.btn_excel = tk.Button(btns, text="📊 Excel", font=('Segoe UI', 9, 'bold'),
                                  bg=C['border'], fg=C['text_soft'], relief='flat',
                                  state=tk.DISABLED, padx=12, pady=5, cursor='hand2',
                                  command=self.abrir_excel)
        self.btn_excel.pack(side=tk.LEFT, padx=(0, 8))
        
        self.btn_stop = tk.Button(btns, text="■ Detener", font=('Segoe UI', 9, 'bold'),
                                 bg=C['error'], fg='white', relief='flat',
                                 state=tk.DISABLED, padx=12, pady=5, cursor='hand2',
                                 command=self.detener)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))
        
        self.btn_start = tk.Button(btns, text="▶ Iniciar", font=('Segoe UI', 9, 'bold'),
                                  bg=C['border'], fg=C['text_soft'], relief='flat',
                                  state=tk.DISABLED, padx=15, pady=5, cursor='hand2',
                                  command=self.iniciar)
        self.btn_start.pack(side=tk.LEFT)
        
        # --- Progreso ---
        prog_frame = tk.Frame(main, bg=C['card'], highlightbackground=C['border'], highlightthickness=1)
        prog_frame.pack(fill=tk.X, pady=(0, 12))
        
        prog_inner = tk.Frame(prog_frame, bg=C['card'])
        prog_inner.pack(fill=tk.X, padx=20, pady=15)
        
        # Porcentaje y estado en línea
        top_prog = tk.Frame(prog_inner, bg=C['card'])
        top_prog.pack(fill=tk.X)
        
        self.lbl_pct = tk.Label(top_prog, text="0%", font=('Segoe UI', 36, 'bold'),
                               fg=C['text_muted'], bg=C['card'])
        self.lbl_pct.pack(side=tk.LEFT)
        
        self.lbl_status = tk.Label(top_prog, text="Esperando archivo...", font=('Segoe UI', 10),
                                  fg=C['text_soft'], bg=C['card'])
        self.lbl_status.pack(side=tk.LEFT, padx=(20, 0))
        
        self.lbl_count = tk.Label(top_prog, text="0 de 0", font=('Segoe UI', 9),
                                 fg=C['text_muted'], bg=C['card'])
        self.lbl_count.pack(side=tk.RIGHT)
        
        # Barra
        self.canvas_bar = tk.Canvas(prog_inner, height=6, bg=C['border'], highlightthickness=0)
        self.canvas_bar.pack(fill=tk.X, pady=(12, 0))
        self.bar_width = 0
        self.canvas_bar.bind('<Configure>', lambda e: self._on_resize(e))
        
        # --- Registro (EXPANDIDO) ---
        log_frame = tk.Frame(main, bg=C['card'], highlightbackground=C['border'], highlightthickness=1)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        log_header = tk.Frame(log_frame, bg=C['card'])
        log_header.pack(fill=tk.X, padx=15, pady=(10, 5))
        tk.Label(log_header, text="📋 Registro de actividad", font=('Segoe UI', 9, 'bold'),
                fg=C['text'], bg=C['card']).pack(side=tk.LEFT)
        
        log_container = tk.Frame(log_frame, bg=C['card'])
        log_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 12))
        
        scrollbar = ttk.Scrollbar(log_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(log_container, font=('Consolas', 9), bg='#F8FAFC',
                               fg=C['text'], relief='flat', bd=0, wrap=tk.WORD,
                               state=tk.DISABLED, yscrollcommand=scrollbar.set, height=8)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # Tags
        self.log_text.tag_configure('time', foreground=C['text_muted'])
        self.log_text.tag_configure('success', foreground=C['success'])
        self.log_text.tag_configure('error', foreground=C['error'])
        self.log_text.tag_configure('warning', foreground=C['warning'])
        self.log_text.tag_configure('info', foreground=C['info'])
        
        # === FOOTER ===
        footer = tk.Frame(self, bg=C['card'], height=38)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)
        
        tk.Frame(footer, bg=C['primary'], height=2).pack(fill=tk.X)
        
        f_inner = tk.Frame(footer, bg=C['card'])
        f_inner.pack(fill=tk.BOTH, expand=True, padx=20)
        
        tk.Label(f_inner, text=f"{APP['company']} • {APP['location']}", font=('Segoe UI', 8),
                fg=C['text_soft'], bg=C['card']).pack(side=tk.LEFT, pady=8)
        
        tk.Label(f_inner, text=f"v{APP['version']} | {APP['dev']}", font=('Segoe UI', 8),
                fg=C['text_soft'], bg=C['card']).pack(side=tk.RIGHT, pady=8)
    
    def _on_resize(self, e):
        self.bar_width = e.width
        self._draw_bar()
    
    def _draw_bar(self):
        self.canvas_bar.delete('all')
        if self.bar_width > 0 and self.progreso_visual > 0:
            w = int((self.progreso_visual / 100) * self.bar_width)
            color = C['success'] if self.progreso_visual >= 100 else C['primary']
            self.canvas_bar.create_rectangle(0, 0, w, 6, fill=color, outline='')
    
    def _start_anim(self):
        if not self.anim_activa:
            self.anim_activa = True
            self._animate()
    
    def _animate(self):
        if not self.anim_activa:
            return
        
        diff = self.progreso_objetivo - self.progreso_visual
        if abs(diff) > 0.5:
            self.progreso_visual += diff * 0.08
            pct = int(self.progreso_visual)
            self.lbl_pct.config(text=f"{pct}%")
            self._draw_bar()
            
            # Color dinámico
            if pct >= 100:
                self.lbl_pct.config(fg=C['success'])
            elif pct >= 50:
                self.lbl_pct.config(fg=C['primary'])
            else:
                self.lbl_pct.config(fg=C['warning'])
        
        self.after(30, self._animate)
    
    def _stop_anim(self):
        self.anim_activa = False
    
    # === ARCHIVOS ===
    def seleccionar_archivo(self):
        f = filedialog.askopenfilename(
            title="Seleccionar archivo de CUFEs",
            filetypes=[("Excel", "*.xlsx"), ("Texto", "*.txt"), ("Todos", "*.*")])
        if f:
            self.archivo_var.set(f)
            nombre = os.path.basename(f)
            self.lbl_archivo.config(text=nombre if len(nombre) < 50 else nombre[:47]+"...", fg=C['text'])
            self.validar_archivo(f)
    
    def seleccionar_carpeta(self):
        d = filedialog.askdirectory(initialdir=self.carpeta_var.get())
        if d:
            self.carpeta_var.set(d)
            self.log(f"Destino: {os.path.basename(d)}", "info")
    
    def validar_archivo(self, path):
        self.log(f"Cargando: {os.path.basename(path)}", "info")
        try:
            cufes = []
            ext = os.path.splitext(path)[1].lower()
            if ext == '.xlsx':
                import pandas as pd
                df = pd.read_excel(path, header=None)
                for col in df.columns:
                    for v in df[col].dropna():
                        t = str(v).strip()
                        if len(t) >= 90:
                            cufes.append(t)
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    cufes = [l.strip() for l in f if l.strip()]
            self._validar_cufes(cufes)
        except Exception as e:
            self.log(f"Error: {e}", "error")
    
    def _validar_cufes(self, cufes):
        import re
        self.cufes_validos = []
        self.cufes_invalidos = []
        seen = set()
        self.duplicados = 0
        
        pat = re.compile(r'^[a-fA-F0-9]{96}$')
        for c in cufes:
            c = c.strip()
            if not pat.match(c):
                self.cufes_invalidos.append(c)
            elif c in seen:
                self.duplicados += 1
            else:
                seen.add(c)
                self.cufes_validos.append(c)
        
        n_ok = len(self.cufes_validos)
        n_bad = len(self.cufes_invalidos)
        
        self.lbl_valid.config(text=f"✓ {n_ok}")
        self.lbl_invalid.config(text=f"✗ {n_bad}")
        self.lbl_dup.config(text=f"◐ {self.duplicados}")
        self.lbl_total.config(text=f"Total: {n_ok}")
        
        if n_ok > 0:
            self.btn_start.config(state=tk.NORMAL, bg=C['success'], fg='white')
            self.lbl_status.config(text="Listo para iniciar")
            self.log(f"✓ {n_ok} CUFEs válidos", "success")
        else:
            self.btn_start.config(state=tk.DISABLED, bg=C['border'], fg=C['text_soft'])
            self.log("No hay CUFEs válidos", "warning")
    
    # === PROCESO ===
    def iniciar(self):
        if not self.cufes_validos:
            return
        
        self.processing = True
        self.stop_requested = False
        
        self.btn_start.config(state=tk.DISABLED, bg=C['border'], fg=C['text_soft'])
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_excel.config(state=tk.DISABLED)
        self.btn_archivo.config(state=tk.DISABLED)
        
        self.total = len(self.cufes_validos)
        self.progreso_visual = 0.0
        self.progreso_objetivo = 0.0
        self._draw_bar()
        
        self.lbl_pct.config(text="0%", fg=C['text_muted'])
        self.lbl_status.config(text="Iniciando...")
        self.lbl_count.config(text=f"0 de {self.total}")
        
        self._start_anim()
        self.log("Iniciando proceso...", "info")
        
        threading.Thread(target=self._procesar, daemon=True).start()
    
    def _procesar(self):
        try:
            if not MODULOS_DISPONIBLES:
                self.log("Módulos no disponibles", "error")
                self.after(0, self._finalizar)
                return
            
            settings = cargar_settings()
            carpeta = self.carpeta_var.get()
            
            # Temporal oculta
            temp = os.path.join(carpeta, ".cufe_temp")
            os.makedirs(temp, exist_ok=True)
            try:
                import platform, subprocess
                if platform.system() == "Windows":
                    subprocess.run(['attrib', '+h', temp], capture_output=True)
            except: pass
            
            pdfs = os.path.join(carpeta, "Facturas_PDF")
            os.makedirs(pdfs, exist_ok=True)
            
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            excel = os.path.join(carpeta, f"Reporte_{ts}.xlsx")
            
            cfg = {
                'dian_url': settings.dian_url,
                'carpeta_pdfs': pdfs,
                'archivo_excel': excel,
                'num_navegadores': min(len(self.cufes_validos), APP['max_nav']),
                'max_reintentos': settings.max_reintentos,
                'carpeta_temp': temp,
            }
            
            def cb_prog(pct, actual, total):
                self.after(0, lambda: self._update_prog(pct, actual, total))
            
            def cb_msg(msg, tipo):
                self.log(msg, tipo)
                self.after(0, lambda: self.lbl_status.config(text=msg[:40]))
            
            res = ejecutar_sistema(self.cufes_validos, cfg,
                                  callback_progreso=cb_prog,
                                  callback_mensaje=cb_msg)
            
            if not self.stop_requested:
                self.resultado = res
                self.excel_path = excel
                
                r = res['resultados']
                ok = len([x for x in r if x['estado'] == 'exitoso'])
                err = len([x for x in r if x['estado'] == 'error'])
                dur = res['duracion']
                
                self.log("─" * 35, "info")
                self.log(f"✓ Completado: {ok} exitosos, {err} errores", "success")
                self.log(f"⏱ Tiempo: {dur:.1f}s", "info")
                
                self.after(0, lambda: self._update_prog(100, self.total, self.total))
            
            self.after(0, self._finalizar)
            
        except Exception as e:
            self.log(f"Error: {e}", "error")
            self.after(0, self._finalizar)
    
    def _update_prog(self, pct, actual, total):
        self.lbl_count.config(text=f"{actual} de {total}")
        obj = (actual / max(total, 1)) * 100
        if obj > self.progreso_objetivo:
            self.progreso_objetivo = obj
        
        if pct >= 100:
            self.progreso_objetivo = 100
            self.progreso_visual = 100
            self._draw_bar()
            self.lbl_pct.config(text="100%", fg=C['success'])
            self.lbl_status.config(text="¡Completado!")
    
    def _finalizar(self):
        self.processing = False
        self._stop_anim()
        
        self.btn_start.config(state=tk.NORMAL, bg=C['success'], fg='white')
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_excel.config(state=tk.NORMAL, bg=C['primary'], fg='white')
        self.btn_archivo.config(state=tk.NORMAL)
    
    def detener(self):
        if messagebox.askyesno("Confirmar", "¿Detener el proceso?"):
            self.stop_requested = True
            self.log("Deteniendo...", "warning")
    
    def abrir_excel(self):
        if self.excel_path and os.path.exists(self.excel_path):
            try:
                import platform
                if platform.system() == 'Windows':
                    os.startfile(self.excel_path)
                else:
                    import webbrowser
                    webbrowser.open(f'file://{self.excel_path}')
                self.log("Abriendo Excel...", "success")
            except Exception as e:
                self.log(f"Error: {e}", "error")
        else:
            messagebox.showinfo("Aviso", "Ejecute el proceso primero")
    
    # === LOG ===
    def log(self, msg, tipo="info"):
        self.log_queue.put((datetime.now().strftime("%H:%M:%S"), msg, tipo))
    
    def process_logs(self):
        try:
            while True:
                ts, msg, tipo = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"[{ts}] ", 'time')
                self.log_text.insert(tk.END, f"{msg}\n", tipo)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(100, self.process_logs)
    
    def on_close(self):
        if self.processing:
            if not messagebox.askyesno("Confirmar", "Hay un proceso activo. ¿Salir?"):
                return
            self.stop_requested = True
        self.destroy()


if __name__ == "__main__":
    print(f"\n{'═'*50}")
    print(f"  CUFE DIAN v{APP['version']} | {APP['dev']}")
    print(f"{'═'*50}\n")
    App().mainloop()