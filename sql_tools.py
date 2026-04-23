"""
SQL Tools - Unified GUI Application
====================================
A standalone GUI application combining 4 SQL processing tools:
1. INSERT Consolidator - Consolidates INSERT statements from MySQL Workbench exports
2. DB Automation Converter - Formats database objects for automation
3. Workfile Generator - Creates standardized SQL files with JIRA folder management
4. Multi-Schema Combiner - Generates a single deployment file for multiple DB schemas

Author: Abhinav Prasad
"""

import importlib
import os
import sys
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Add project root to path for dynamic imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


# ============================================================================
# FEATURE PROFILES - Build-time feature subset support
# ============================================================================
FEATURE_INSERT_CONSOLIDATOR = "INSERT_CONSOLIDATOR"
FEATURE_DB_AUTOMATION = "DB_AUTOMATION"
FEATURE_WORKFILE_GENERATOR = "WORKFILE_GENERATOR"
FEATURE_MULTI_SCHEMA = "MULTI_SCHEMA"

ALL_FEATURES = [
    FEATURE_INSERT_CONSOLIDATOR,
    FEATURE_DB_AUTOMATION,
    FEATURE_WORKFILE_GENERATOR,
    FEATURE_MULTI_SCHEMA,
]

FEATURE_TAB_LABELS = {
    FEATURE_INSERT_CONSOLIDATOR: "  INSERT Consolidator  ",
    FEATURE_DB_AUTOMATION: "  DB Automation Converter  ",
    FEATURE_WORKFILE_GENERATOR: "  Workfile Generator  ",
    FEATURE_MULTI_SCHEMA: "  Multi-Schema Combiner  ",
}

FEATURE_TO_LOGIC_MODULE = {
    FEATURE_INSERT_CONSOLIDATOR: "logic.insert_consolidator",
    FEATURE_DB_AUTOMATION: "logic.db_automation",
    FEATURE_WORKFILE_GENERATOR: "logic.workfile_generator",
    FEATURE_MULTI_SCHEMA: "logic.multi_schema_combiner",
}


def _normalize_features(features):
    """Normalize and validate feature identifiers while preserving canonical order."""
    seen = set()
    normalized = []
    upper_tokens = {str(item).strip().upper() for item in features if str(item).strip()}
    for feature in ALL_FEATURES:
        if feature in upper_tokens and feature not in seen:
            normalized.append(feature)
            seen.add(feature)
    return normalized


def _load_enabled_features():
    """
    Resolve enabled features from build metadata.
    Priority:
    1) SQL_TOOLS_FEATURES env var (set by build.bat during build/test)
    2) generated/build_profile.py (packaged artifact metadata)
    3) fallback to full feature set
    """
    raw_env = os.environ.get("SQL_TOOLS_FEATURES", "").strip()
    if raw_env:
        parsed = _normalize_features(raw_env.split(","))
        if parsed:
            return parsed

    profile_path = os.path.join(SCRIPT_DIR, "generated", "build_profile.py")
    if os.path.exists(profile_path):
        namespace = {}
        with open(profile_path, "r", encoding="utf-8") as profile_file:
            exec(profile_file.read(), namespace)
        parsed = _normalize_features(namespace.get("ENABLED_FEATURES", []))
        if parsed:
            return parsed

    return list(ALL_FEATURES)


ENABLED_FEATURES = _load_enabled_features()

ENABLE_INSERT_CONSOLIDATOR = FEATURE_INSERT_CONSOLIDATOR in ENABLED_FEATURES
ENABLE_DB_AUTOMATION = FEATURE_DB_AUTOMATION in ENABLED_FEATURES
ENABLE_WORKFILE_GENERATOR = FEATURE_WORKFILE_GENERATOR in ENABLED_FEATURES
ENABLE_MULTI_SCHEMA = FEATURE_MULTI_SCHEMA in ENABLED_FEATURES


# ============================================================================
# STYLING CONSTANTS - Organization Theme (Purple + Yellow/Cream)
# ============================================================================
COLORS = {
    'bg': '#FFF8ED',              # Main background (cream/yellowish)
    'bg_light': '#FFF0DB',        # Slightly darker cream for sections
    'bg_input': '#FFFFFF',        # White for input fields
    'fg': '#1a1a1a',              # Main text (near black)
    'fg_dim': '#666666',          # Dimmed text
    'accent': '#623a96',          # Primary purple
    'accent_hover': '#7a4db8',    # Lighter purple for hover
    'accent_light': '#f0e8f7',    # Very light purple for backgrounds
    'success': '#2e7d32',         # Green for success
    'error': '#c62828',           # Red for errors
    'warning': '#f57c00',         # Orange for warnings
    'border': '#d4c4a8'           # Border color (warm beige)
}

FONTS = {
    'heading': ('Segoe UI', 13, 'bold'),
    'subheading': ('Segoe UI', 10),
    'label': ('Segoe UI', 9),
    'input': ('Consolas', 10),
    'button': ('Segoe UI', 9, 'bold'),
    'status': ('Consolas', 9),
    'footer': ('Segoe UI', 8)
}


# ============================================================================
# MAIN APPLICATION CLASS
# ============================================================================
class SQLToolsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SQL Tools")
        self.root.geometry("1200x700")
        self.root.minsize(1000, 600)

        self.enabled_features = list(ENABLED_FEATURES)
        self._logic_modules = {}
        self._feature_tabs = {}
        self._tab_id_to_feature = {}
        self._feature_initialized = {feature: False for feature in self.enabled_features}
        self._feature_builders = {
            FEATURE_INSERT_CONSOLIDATOR: self.create_insert_consolidator_tab,
            FEATURE_DB_AUTOMATION: self.create_db_automation_tab,
            FEATURE_WORKFILE_GENERATOR: self.create_workfile_generator_tab,
            FEATURE_MULTI_SCHEMA: self.create_multi_schema_tab,
        }

        # Configure root styling
        self.root.configure(bg=COLORS['bg'])

        # Configure ttk styles
        self.configure_styles()

        # Create main container
        self.main_frame = ttk.Frame(root, style='Main.TFrame')
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Create header
        self.create_header()

        if not self.enabled_features:
            self.notebook = None
            self.single_feature_container = ttk.Frame(self.main_frame, style='Main.TFrame')
            self.single_feature_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 10))
            ttk.Label(
                self.single_feature_container,
                text="No features are enabled in this build profile.",
                style="Heading.TLabel",
            ).pack(anchor="w", padx=10, pady=10)
        elif len(self.enabled_features) == 1:
            self.notebook = None
            self.single_feature_container = ttk.Frame(self.main_frame, style='Main.TFrame')
            self.single_feature_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 10))
            self._ensure_feature_initialized(self.enabled_features[0])
        else:
            self.single_feature_container = None
            self.notebook = ttk.Notebook(self.main_frame, style='Custom.TNotebook')
            self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 10))

            for feature in self.enabled_features:
                placeholder_tab = ttk.Frame(self.notebook, style='Tab.TFrame')
                self.notebook.add(placeholder_tab, text=FEATURE_TAB_LABELS[feature])
                self._feature_tabs[feature] = placeholder_tab
                self._tab_id_to_feature[str(placeholder_tab)] = feature

            self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)
            self._ensure_feature_initialized(self.enabled_features[0])

        # Create footer with author
        self.create_footer()
    
    def configure_styles(self):
        """Configure ttk styles for light theme."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Frame styles
        style.configure('Main.TFrame', background=COLORS['bg'])
        style.configure('Tab.TFrame', background=COLORS['bg'])
        style.configure('Options.TFrame', background=COLORS['bg'])
        style.configure('Status.TFrame', background=COLORS['bg_light'])
        
        # Notebook styling
        style.configure('Custom.TNotebook', background=COLORS['bg'], borderwidth=0)
        style.configure('Custom.TNotebook.Tab', 
                       background=COLORS['bg_light'],
                       foreground=COLORS['fg'],
                       padding=[20, 8],
                       font=FONTS['label'])
        style.map('Custom.TNotebook.Tab',
                 background=[('selected', COLORS['accent'])],
                 foreground=[('selected', '#FFFFFF')])
        
        # Label styles
        style.configure('TLabel', 
                       background=COLORS['bg'],
                       foreground=COLORS['fg'],
                       font=FONTS['label'])
        style.configure('Heading.TLabel',
                       background=COLORS['bg'],
                       foreground=COLORS['accent'],
                       font=FONTS['heading'])
        style.configure('Status.TLabel',
                       background=COLORS['bg_light'],
                       foreground=COLORS['fg'],
                       font=FONTS['label'])
        
        # Radiobutton styles
        style.configure('TRadiobutton',
                       background=COLORS['bg'],
                       foreground=COLORS['fg'],
                       font=FONTS['label'])
        
        # Checkbutton styles
        style.configure('TCheckbutton',
                       background=COLORS['bg'],
                       foreground=COLORS['fg'],
                       font=FONTS['label'])
        
        # LabelFrame styles
        style.configure('TLabelframe',
                       background=COLORS['bg'],
                       foreground=COLORS['fg'],
                       bordercolor=COLORS['border'])
        style.configure('TLabelframe.Label',
                       background=COLORS['bg'],
                       foreground=COLORS['accent'],
                       font=FONTS['label'])
    
    def create_header(self):
        """Create application header."""
        header = ttk.Frame(self.main_frame, style='Main.TFrame')
        header.pack(fill=tk.X, padx=15, pady=(15, 5))
        
        title = ttk.Label(header, text="SQL Tools", style='Heading.TLabel')
        title.pack(side=tk.LEFT)

    def _get_logic_module(self, feature_name):
        """Lazily import and cache logic modules for enabled features."""
        module = self._logic_modules.get(feature_name)
        if module is None:
            module = importlib.import_module(FEATURE_TO_LOGIC_MODULE[feature_name])
            self._logic_modules[feature_name] = module
        return module

    def _resolve_tab_container(self, feature_name, tab=None, add_to_notebook=True):
        """Return the container frame for a feature view (notebook tab or single-view frame)."""
        if tab is not None:
            return tab

        if self.notebook is not None:
            tab = ttk.Frame(self.notebook, style='Tab.TFrame')
            if add_to_notebook:
                self.notebook.add(tab, text=FEATURE_TAB_LABELS[feature_name])
            return tab

        tab = ttk.Frame(self.single_feature_container, style='Tab.TFrame')
        tab.pack(fill=tk.BOTH, expand=True)
        return tab

    def _ensure_feature_initialized(self, feature_name):
        """Create feature UI only when needed to speed up initial startup."""
        if self._feature_initialized.get(feature_name):
            return

        tab = self._feature_tabs.get(feature_name)
        if tab is not None:
            for child in tab.winfo_children():
                child.destroy()

        builder = self._feature_builders[feature_name]
        builder(tab=tab, add_to_notebook=False)
        self._feature_initialized[feature_name] = True

    def _on_notebook_tab_changed(self, _event):
        """Lazy-load feature UI for tabs only when first opened."""
        selected_tab_id = self.notebook.select()
        feature_name = self._tab_id_to_feature.get(selected_tab_id)
        if feature_name:
            self._ensure_feature_initialized(feature_name)
    
    def create_text_widget(self, parent, height=10):
        """Create a styled scrolled text widget."""
        frame = tk.Frame(parent, bg=COLORS['border'], padx=1, pady=1)
        text = scrolledtext.ScrolledText(
            frame,
            height=height,
            bg=COLORS['bg_input'],
            fg=COLORS['fg'],
            insertbackground=COLORS['fg'],
            font=FONTS['input'],
            relief=tk.FLAT,
            padx=8,
            pady=8,
            wrap=tk.NONE
        )
        text.pack(fill=tk.BOTH, expand=True)
        return frame, text
    
    def create_entry_widget(self, parent, width=30):
        """Create a styled entry widget."""
        frame = tk.Frame(parent, bg=COLORS['border'], padx=1, pady=1)
        entry = tk.Entry(
            frame,
            width=width,
            bg=COLORS['bg_input'],
            fg=COLORS['fg'],
            insertbackground=COLORS['fg'],
            font=FONTS['input'],
            relief=tk.FLAT
        )
        entry.pack(fill=tk.X, ipady=4)
        return frame, entry
    
    def create_button(self, parent, text, command, style='primary'):
        """Create a styled button."""
        if style == 'primary':
            bg = COLORS['accent']
            fg = '#FFFFFF'
            hover_bg = COLORS['accent_hover']
        else:
            bg = COLORS['bg_light']
            fg = COLORS['fg']
            hover_bg = COLORS['border']
        
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            font=FONTS['button'],
            relief=tk.FLAT,
            cursor='hand2',
            padx=12,
            pady=6,
            bd=0
        )
        
        # Hover effects
        def on_enter(e):
            if btn['state'] != tk.DISABLED:
                btn.configure(bg=hover_bg)
        def on_leave(e):
            if btn['state'] != tk.DISABLED:
                btn.configure(bg=bg)
        
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        
        return btn
    
    def browse_folder(self, entry_widget):
        """Open folder browser dialog."""
        folder = filedialog.askdirectory()
        if folder:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, folder)
    
    # ========================================================================
    # TAB 1: INSERT CONSOLIDATOR
    # ========================================================================
    def create_insert_consolidator_tab(self, tab=None, add_to_notebook=True):
        """Create the INSERT Consolidator tab with simplified single-page layout."""
        tab = self._resolve_tab_container(FEATURE_INSERT_CONSOLIDATOR, tab, add_to_notebook)
        
        # Main horizontal container
        main_container = ttk.Frame(tab, style='Tab.TFrame')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel (Input + Options)
        left_panel = ttk.Frame(main_container, style='Tab.TFrame')
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right panel (Status)
        right_panel = ttk.Frame(main_container, style='Status.TFrame')
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(15, 0), ipadx=10, ipady=10)
        right_panel.configure(width=350)
        right_panel.pack_propagate(False)
        
        # === LEFT PANEL CONTENT ===
        
        # --- Paste SQL Section (on top, resizable) ---
        paste_frame = ttk.LabelFrame(left_panel, text=" Paste SQL (optional - takes priority) ", style='TLabelframe')
        paste_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.ic_input_text_frame, self.ic_input_text = self.create_text_widget(paste_frame, 8)
        self.ic_input_text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- Or Section Label ---
        or_label = ttk.Label(left_panel, text="─── OR select source ───", style='TLabel')
        or_label.pack(pady=5)
        
        # --- Source Section ---
        source_frame = ttk.Frame(left_panel, style='Tab.TFrame')
        source_frame.pack(fill=tk.X, pady=5)
        
        # Folder row
        folder_row = ttk.Frame(source_frame, style='Tab.TFrame')
        folder_row.pack(fill=tk.X, pady=2)
        ttk.Label(folder_row, text="Input Folder:", style='TLabel', width=12).pack(side=tk.LEFT)
        self.ic_input_folder_frame, self.ic_input_folder = self.create_entry_widget(folder_row, 40)
        self.ic_input_folder_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.create_button(folder_row, "Browse", lambda: self.browse_folder(self.ic_input_folder), 'secondary').pack(side=tk.LEFT)
        
        # Files row
        files_row = ttk.Frame(source_frame, style='Tab.TFrame')
        files_row.pack(fill=tk.X, pady=2)
        ttk.Label(files_row, text="Select Files:", style='TLabel', width=12).pack(side=tk.LEFT)
        self.ic_selected_files = []
        self.ic_files_label = ttk.Label(files_row, text="No files selected", style='TLabel')
        self.ic_files_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.create_button(files_row, "Select Files", self.ic_browse_files, 'secondary').pack(side=tk.LEFT)
        self.create_button(files_row, "Clear", self.ic_clear_files, 'secondary').pack(side=tk.LEFT, padx=(5, 0))
        
        # --- Options Section ---
        options_frame = ttk.LabelFrame(left_panel, text=" Options ", style='TLabelframe')
        options_frame.pack(fill=tk.X, pady=10)
        options_inner = ttk.Frame(options_frame, style='Tab.TFrame')
        options_inner.pack(fill=tk.X, padx=10, pady=10)
        
        # Output folder row (always visible)
        out_row = ttk.Frame(options_inner, style='Tab.TFrame')
        out_row.pack(fill=tk.X, pady=3)
        ttk.Label(out_row, text="Output Folder:", style='TLabel', width=16).pack(side=tk.LEFT)
        self.ic_output_folder_frame, self.ic_output_folder = self.create_entry_widget(out_row, 35)
        self.ic_output_folder_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.create_button(out_row, "Browse", lambda: self.browse_folder(self.ic_output_folder), 'secondary').pack(side=tk.LEFT)
        
        # Modify in-place checkbox
        self.ic_modify_in_place = tk.BooleanVar(value=False)
        in_place_row = ttk.Frame(options_inner, style='Tab.TFrame')
        in_place_row.pack(fill=tk.X, pady=3)
        ttk.Label(in_place_row, text="", width=16).pack(side=tk.LEFT)
        ttk.Checkbutton(in_place_row, text="Modify files in-place (folder mode only)",
                       variable=self.ic_modify_in_place).pack(side=tk.LEFT)
        
        # Date prefix row
        date_row = ttk.Frame(options_inner, style='Tab.TFrame')
        date_row.pack(fill=tk.X, pady=3)
        ttk.Label(date_row, text="Date Prefix:", style='TLabel', width=16).pack(side=tk.LEFT)
        self.ic_date_prefix_frame, self.ic_date_prefix = self.create_entry_widget(date_row, 15)
        self.ic_date_prefix.insert(0, datetime.now().strftime("%Y%m%d"))
        self.ic_date_prefix_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(date_row, text="(editable)", style='TLabel', foreground=COLORS['fg_dim']).pack(side=tk.LEFT)
        
        # Checkboxes row
        checks_row = ttk.Frame(options_inner, style='Tab.TFrame')
        checks_row.pack(fill=tk.X, pady=3)
        ttk.Label(checks_row, text="", width=16).pack(side=tk.LEFT)
        
        self.ic_generate_combined = tk.BooleanVar(value=False)
        ttk.Checkbutton(checks_row, text="Combined SQL file",
                       variable=self.ic_generate_combined).pack(side=tk.LEFT)
        
        self.ic_generate_excel = tk.BooleanVar(value=True)
        ttk.Checkbutton(checks_row, text="Excel summary",
                       variable=self.ic_generate_excel).pack(side=tk.LEFT, padx=(15, 0))
        
        # Execute buttons
        btn_frame = ttk.Frame(left_panel, style='Tab.TFrame')
        btn_frame.pack(fill=tk.X, pady=10)
        self.create_button(btn_frame, "▶  Execute", self.ic_execute).pack(side=tk.LEFT)
        self.create_button(btn_frame, "Clear All", self.ic_clear, 'secondary').pack(side=tk.LEFT, padx=10)
        
        # === RIGHT PANEL CONTENT (Status) ===
        status_title = tk.Label(right_panel, text="Status / Results", font=FONTS['heading'],
                               bg=COLORS['bg_light'], fg=COLORS['accent'])
        status_title.pack(anchor='w', pady=(5, 10))
        
        self.ic_status_frame, self.ic_status = self.create_text_widget(right_panel, 20)
        self.ic_status_frame.pack(fill=tk.BOTH, expand=True)
        self.ic_status.configure(state='disabled', bg=COLORS['bg_light'])
        
        # Copy button
        copy_btn = self.create_button(right_panel, "📋 Copy to Clipboard", self.ic_copy_status, 'secondary')
        copy_btn.pack(anchor='e', pady=(10, 0))
    
    def ic_browse_files(self):
        """Open file browser dialog for multiple files."""
        files = filedialog.askopenfilenames(
            title="Select SQL Files",
            filetypes=[("SQL Files", "*.sql"), ("All Files", "*.*")]
        )
        if files:
            self.ic_selected_files = list(files)
            if len(files) == 1:
                self.ic_files_label.configure(text=os.path.basename(files[0]))
            else:
                self.ic_files_label.configure(text=f"{len(files)} files selected")
    
    def ic_clear_files(self):
        """Clear selected files."""
        self.ic_selected_files = []
        self.ic_files_label.configure(text="No files selected")
    
    def ic_clear(self):
        """Clear all inputs."""
        self.ic_input_text.delete('1.0', tk.END)
        self.ic_input_folder.delete(0, tk.END)
        self.ic_clear_files()
        self.ic_status.configure(state='normal')
        self.ic_status.delete('1.0', tk.END)
        self.ic_status.configure(state='disabled')
    
    def ic_copy_status(self):
        """Copy status text to clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.ic_status.get('1.0', tk.END))
        messagebox.showinfo("Copied", "Status copied to clipboard")
    
    def ic_execute(self):
        """Execute INSERT consolidation. Priority: paste > files > folder"""
        date_prefix = self.ic_date_prefix.get().strip()
        if not date_prefix:
            date_prefix = datetime.now().strftime("%Y%m%d")
        
        generate_combined = self.ic_generate_combined.get()
        generate_excel = self.ic_generate_excel.get()
        
        self.ic_status.configure(state='normal')
        self.ic_status.delete('1.0', tk.END)
        
        try:
            insert_logic = self._get_logic_module(FEATURE_INSERT_CONSOLIDATOR)
            # Determine input mode by priority: paste > files > folder
            raw_text = self.ic_input_text.get('1.0', tk.END).strip()
            
            if raw_text:
                # Paste mode
                output_folder = self.ic_output_folder.get().strip()
                if not output_folder:
                    messagebox.showerror("Error", "Please select an output folder")
                    return
                
                results = insert_logic.process_pasted_to_files(
                    raw_text, output_folder, date_prefix, generate_combined
                )
                mode_used = "paste"
                
            elif self.ic_selected_files:
                # Files mode
                output_folder = self.ic_output_folder.get().strip()
                if not output_folder:
                    messagebox.showerror("Error", "Please select an output folder")
                    return
                
                results = insert_logic.process_files(
                    self.ic_selected_files, output_folder, date_prefix, generate_combined
                )
                mode_used = "files"
                
            else:
                # Folder mode
                input_folder = self.ic_input_folder.get().strip()
                if not input_folder:
                    messagebox.showerror("Error", "Please provide input: paste SQL, select files, or choose a folder")
                    return
                
                # Use input folder as output if modify in-place
                if self.ic_modify_in_place.get():
                    output_folder = input_folder
                else:
                    output_folder = self.ic_output_folder.get().strip()
                    if not output_folder:
                        messagebox.showerror("Error", "Please select an output folder (or enable 'modify in-place')")
                        return
                
                results = insert_logic.process_folder(
                    input_folder, output_folder, date_prefix, generate_combined
                )
                mode_used = "folder"
            
            # Display results with stats
            total_records = 0
            self.ic_status.insert(tk.END, f"═══════════════════════════════════════\n")
            self.ic_status.insert(tk.END, f"  PROCESSING COMPLETE ({mode_used} mode)\n")
            self.ic_status.insert(tk.END, f"═══════════════════════════════════════\n\n")
            self.ic_status.insert(tk.END, f"✓ Files processed: {len(results['processed'])}\n\n")
            
            self.ic_status.insert(tk.END, f"{'File':<35} {'Table':<20} {'Records':>8}\n")
            self.ic_status.insert(tk.END, f"{'─'*35} {'─'*20} {'─'*8}\n")
            
            for item in results['processed']:
                table = item.get('table', 'unknown')
                output = item.get('output', item.get('input', 'unknown'))
                records = item.get('records', 0)
                total_records += records
                self.ic_status.insert(tk.END, f"{output:<35} {table:<20} {records:>8}\n")
            
            self.ic_status.insert(tk.END, f"{'─'*35} {'─'*20} {'─'*8}\n")
            self.ic_status.insert(tk.END, f"{'TOTAL':<56} {total_records:>8}\n\n")
            
            if results.get('combined_file'):
                self.ic_status.insert(tk.END, f"✓ Combined file: {results['combined_file']}\n")
            
            # Generate Excel if requested
            if generate_excel and results['processed']:
                excel_file = insert_logic.generate_excel_summary(
                    results['processed'], output_folder, date_prefix
                )
                if excel_file:
                    self.ic_status.insert(tk.END, f"✓ Excel summary: {excel_file}\n")
                else:
                    self.ic_status.insert(tk.END, f"⚠ Excel: openpyxl not installed (pip install openpyxl)\n")
            
            if results['errors']:
                self.ic_status.insert(tk.END, f"\n⚠ ERRORS:\n")
                for error in results['errors']:
                    self.ic_status.insert(tk.END, f"  • {error}\n")
                    
        except Exception as e:
            self.ic_status.insert(tk.END, f"✗ Error: {str(e)}\n")
        finally:
            self.ic_status.configure(state='disabled')
    
    # ========================================================================
    # TAB 2: DB AUTOMATION CONVERTER
    # ========================================================================
    def create_db_automation_tab(self, tab=None, add_to_notebook=True):
        """Create the DB Automation Converter tab with side-by-side layout."""
        tab = self._resolve_tab_container(FEATURE_DB_AUTOMATION, tab, add_to_notebook)
        
        # Main horizontal container
        main_container = ttk.Frame(tab, style='Tab.TFrame')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel (Input + Options)
        left_panel = ttk.Frame(main_container, style='Tab.TFrame')
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right panel (Status)
        right_panel = ttk.Frame(main_container, style='Status.TFrame')
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(15, 0), ipadx=10, ipady=10)
        right_panel.configure(width=350)
        right_panel.pack_propagate(False)
        
        # === LEFT PANEL CONTENT ===
        
        # Input mode selection
        mode_frame = ttk.Frame(left_panel, style='Tab.TFrame')
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(mode_frame, text="Input Mode:", style='TLabel').pack(side=tk.LEFT)
        
        self.da_input_mode = tk.StringVar(value="paste")
        ttk.Radiobutton(mode_frame, text="Paste SQL", variable=self.da_input_mode,
                       value="paste", command=self.da_toggle_input_mode).pack(side=tk.LEFT, padx=(10, 5))
        ttk.Radiobutton(mode_frame, text="Select Folder", variable=self.da_input_mode,
                       value="folder", command=self.da_toggle_input_mode).pack(side=tk.LEFT, padx=5)
        
        # Text input frame (shown by default)
        self.da_text_frame = ttk.Frame(left_panel, style='Tab.TFrame')
        self.da_text_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        ttk.Label(self.da_text_frame, text="Paste SQL (procedures, functions, triggers):", style='TLabel').pack(anchor='w')
        self.da_input_text_frame, self.da_input_text = self.create_text_widget(self.da_text_frame, 12)
        self.da_input_text_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # Folder input frame (hidden by default)
        self.da_folder_frame = ttk.Frame(left_panel, style='Tab.TFrame')
        
        folder_row = ttk.Frame(self.da_folder_frame, style='Tab.TFrame')
        folder_row.pack(fill=tk.X)
        ttk.Label(folder_row, text="Input Folder:", style='TLabel', width=12).pack(side=tk.LEFT)
        self.da_input_folder_frame, self.da_input_folder = self.create_entry_widget(folder_row, 50)
        self.da_input_folder_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.create_button(folder_row, "Browse", lambda: self.browse_folder(self.da_input_folder), 'secondary').pack(side=tk.LEFT)
        
        # Options section
        options_frame = ttk.LabelFrame(left_panel, text=" Options ", style='TLabelframe')
        options_frame.pack(fill=tk.X, pady=10)
        options_inner = ttk.Frame(options_frame, style='Tab.TFrame')
        options_inner.pack(fill=tk.X, padx=10, pady=10)
        
        # Output folder row
        out_row = ttk.Frame(options_inner, style='Tab.TFrame')
        out_row.pack(fill=tk.X, pady=3)
        ttk.Label(out_row, text="Output Folder:", style='TLabel', width=14).pack(side=tk.LEFT)
        self.da_output_folder_frame, self.da_output_folder = self.create_entry_widget(out_row, 40)
        self.da_output_folder_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.create_button(out_row, "Browse", lambda: self.browse_folder(self.da_output_folder), 'secondary').pack(side=tk.LEFT)
        
        # Starting sequence row
        seq_row = ttk.Frame(options_inner, style='Tab.TFrame')
        seq_row.pack(fill=tk.X, pady=3)
        ttk.Label(seq_row, text="Start Sequence:", style='TLabel', width=14).pack(side=tk.LEFT)
        self.da_start_seq_frame, self.da_start_seq = self.create_entry_widget(seq_row, 8)
        self.da_start_seq.insert(0, "01")
        self.da_start_seq_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(seq_row, text="(auto-increments)", style='TLabel').pack(side=tk.LEFT, padx=10)
        
        # Developer name row
        dev_row = ttk.Frame(options_inner, style='Tab.TFrame')
        dev_row.pack(fill=tk.X, pady=3)
        ttk.Label(dev_row, text="Developer:", style='TLabel', width=14).pack(side=tk.LEFT)
        self.da_developer_frame, self.da_developer = self.create_entry_widget(dev_row, 30)
        self.da_developer.insert(0, "Abhinav Prasad")
        self.da_developer_frame.pack(side=tk.LEFT, padx=5)
        
        # Execute buttons
        btn_frame = ttk.Frame(left_panel, style='Tab.TFrame')
        btn_frame.pack(fill=tk.X, pady=10)
        self.create_button(btn_frame, "▶  Execute", self.da_execute).pack(side=tk.LEFT)
        self.create_button(btn_frame, "Clear", self.da_clear, 'secondary').pack(side=tk.LEFT, padx=10)
        
        # === RIGHT PANEL CONTENT (Status) ===
        status_title = tk.Label(right_panel, text="Status / Results", font=FONTS['heading'],
                               bg=COLORS['bg_light'], fg=COLORS['accent'])
        status_title.pack(anchor='w', pady=(5, 10))
        
        self.da_status_frame, self.da_status = self.create_text_widget(right_panel, 20)
        self.da_status_frame.pack(fill=tk.BOTH, expand=True)
        self.da_status.configure(state='disabled', bg=COLORS['bg_light'])
        
        # Copy button
        copy_btn = self.create_button(right_panel, "📋 Copy to Clipboard", self.da_copy_status, 'secondary')
        copy_btn.pack(anchor='e', pady=(10, 0))
    
    def da_toggle_input_mode(self):
        """Toggle between paste and folder input modes."""
        if self.da_input_mode.get() == "paste":
            self.da_folder_frame.pack_forget()
            self.da_text_frame.pack(fill=tk.BOTH, expand=True, pady=5, after=self.da_folder_frame.master.winfo_children()[0])
        else:
            self.da_text_frame.pack_forget()
            self.da_folder_frame.pack(fill=tk.X, pady=5, after=self.da_folder_frame.master.winfo_children()[0])
    
    def da_clear(self):
        """Clear all inputs."""
        self.da_input_text.delete('1.0', tk.END)
        self.da_input_folder.delete(0, tk.END)
        self.da_status.configure(state='normal')
        self.da_status.delete('1.0', tk.END)
        self.da_status.configure(state='disabled')
    
    def da_copy_status(self):
        """Copy status text to clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.da_status.get('1.0', tk.END))
        messagebox.showinfo("Copied", "Status copied to clipboard")
    
    def da_execute(self):
        """Execute DB automation conversion."""
        output_folder = self.da_output_folder.get().strip()
        developer = self.da_developer.get().strip()
        
        if not output_folder:
            messagebox.showerror("Error", "Please select an output folder")
            return
        
        try:
            start_seq = int(self.da_start_seq.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Starting sequence must be a number")
            return
        
        self.da_status.configure(state='normal')
        self.da_status.delete('1.0', tk.END)
        
        try:
            db_logic = self._get_logic_module(FEATURE_DB_AUTOMATION)
            if self.da_input_mode.get() == "paste":
                raw_text = self.da_input_text.get('1.0', tk.END).strip()
                if not raw_text:
                    messagebox.showerror("Error", "Please paste SQL content")
                    return
                
                results = db_logic.process_pasted_to_files(
                    raw_text, output_folder, start_seq, developer
                )
            else:
                input_folder = self.da_input_folder.get().strip()
                if not input_folder:
                    messagebox.showerror("Error", "Please select an input folder")
                    return
                
                results = db_logic.process_folder(
                    input_folder, output_folder, start_seq, developer
                )
            
            # Display results with type breakdown
            self.da_status.insert(tk.END, f"═══════════════════════════════════════\n")
            self.da_status.insert(tk.END, f"  PROCESSING COMPLETE\n")
            self.da_status.insert(tk.END, f"═══════════════════════════════════════\n\n")
            
            # Count by type
            type_counts = {}
            for item in results['processed']:
                obj_type = item.get('type', 'PROCEDURE')
                type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
            
            self.da_status.insert(tk.END, f"Summary:\n")
            for obj_type, count in type_counts.items():
                self.da_status.insert(tk.END, f"  • {obj_type}S: {count}\n")
            self.da_status.insert(tk.END, f"  ─────────────────\n")
            self.da_status.insert(tk.END, f"  TOTAL: {len(results['processed'])}\n\n")
            
            self.da_status.insert(tk.END, f"Files created:\n")
            for item in results['processed']:
                seq = item.get('sequence', '??')
                output = item.get('output', 'unknown')
                obj_type = item.get('type', 'SP')[:2]
                self.da_status.insert(tk.END, f"  [{seq:02d}] [{obj_type}] {output}\n")
            
            if results['errors']:
                self.da_status.insert(tk.END, f"\n⚠ ERRORS:\n")
                for error in results['errors']:
                    self.da_status.insert(tk.END, f"  • {error}\n")
                    
        except Exception as e:
            self.da_status.insert(tk.END, f"✗ Error: {str(e)}\n")
        finally:
            self.da_status.configure(state='disabled')
    
    # ========================================================================
    # TAB 3: WORKFILE GENERATOR
    # ========================================================================
    def create_workfile_generator_tab(self, tab=None, add_to_notebook=True):
        """Create the Workfile Generator tab with side-by-side layout."""
        tab = self._resolve_tab_container(FEATURE_WORKFILE_GENERATOR, tab, add_to_notebook)
        
        # Main horizontal container
        main_container = ttk.Frame(tab, style='Tab.TFrame')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel (Input + Options)
        left_panel = ttk.Frame(main_container, style='Tab.TFrame')
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right panel (Status)
        right_panel = ttk.Frame(main_container, style='Status.TFrame')
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(15, 0), ipadx=10, ipady=10)
        right_panel.configure(width=350)
        right_panel.pack_propagate(False)
        
        # === LEFT PANEL CONTENT ===
        
        # Input section
        ttk.Label(left_panel, text="Paste SQL (procedures, functions, triggers, views):", style='TLabel').pack(anchor='w')
        self.wg_input_text_frame, self.wg_input_text = self.create_text_widget(left_panel, 12)
        self.wg_input_text_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        # Options section
        options_frame = ttk.LabelFrame(left_panel, text=" Options ", style='TLabelframe')
        options_frame.pack(fill=tk.X, pady=5)
        options_inner = ttk.Frame(options_frame, style='Tab.TFrame')
        options_inner.pack(fill=tk.X, padx=10, pady=10)
        
        # Base folder row
        base_row = ttk.Frame(options_inner, style='Tab.TFrame')
        base_row.pack(fill=tk.X, pady=3)
        ttk.Label(base_row, text="Base Folder:", style='TLabel', width=14).pack(side=tk.LEFT)
        self.wg_base_folder_frame, self.wg_base_folder = self.create_entry_widget(base_row, 40)
        self.wg_base_folder_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.create_button(base_row, "Browse", lambda: self.browse_folder(self.wg_base_folder), 'secondary').pack(side=tk.LEFT)
        
        # JIRA number row
        jira_row = ttk.Frame(options_inner, style='Tab.TFrame')
        jira_row.pack(fill=tk.X, pady=3)
        ttk.Label(jira_row, text="JIRA Number:", style='TLabel', width=14).pack(side=tk.LEFT)
        self.wg_jira_frame, self.wg_jira = self.create_entry_widget(jira_row, 12)
        self.wg_jira_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(jira_row, text="(for header OP-xxxx)", style='TLabel').pack(side=tk.LEFT, padx=5)
        
        # Create JIRA folder checkbox
        self.wg_create_jira_folder = tk.BooleanVar(value=True)
        jira_folder_row = ttk.Frame(options_inner, style='Tab.TFrame')
        jira_folder_row.pack(fill=tk.X, pady=3)
        ttk.Label(jira_folder_row, text="", width=14).pack(side=tk.LEFT)
        ttk.Checkbutton(jira_folder_row, text="Create JIRA folder (OP - {num} [desc])",
                       variable=self.wg_create_jira_folder).pack(side=tk.LEFT)
        
        # Description row
        desc_row = ttk.Frame(options_inner, style='Tab.TFrame')
        desc_row.pack(fill=tk.X, pady=3)
        ttk.Label(desc_row, text="Description:", style='TLabel', width=14).pack(side=tk.LEFT)
        self.wg_description_frame, self.wg_description = self.create_entry_widget(desc_row, 35)
        self.wg_description_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(desc_row, text="(optional)", style='TLabel').pack(side=tk.LEFT, padx=5)
        
        # Developer row
        dev_row = ttk.Frame(options_inner, style='Tab.TFrame')
        dev_row.pack(fill=tk.X, pady=3)
        ttk.Label(dev_row, text="Developer:", style='TLabel', width=14).pack(side=tk.LEFT)
        self.wg_developer_frame, self.wg_developer = self.create_entry_widget(dev_row, 25)
        self.wg_developer.insert(0, "Abhinav Prasad")
        self.wg_developer_frame.pack(side=tk.LEFT, padx=5)
        
        # Temp prefix row
        prefix_row = ttk.Frame(options_inner, style='Tab.TFrame')
        prefix_row.pack(fill=tk.X, pady=3)
        ttk.Label(prefix_row, text="Temp Prefix:", style='TLabel', width=14).pack(side=tk.LEFT)
        self.wg_temp_prefix_frame, self.wg_temp_prefix = self.create_entry_widget(prefix_row, 15)
        self.wg_temp_prefix.insert(0, "temp_ap_")
        self.wg_temp_prefix_frame.pack(side=tk.LEFT, padx=5)
        
        # Execute buttons
        btn_frame = ttk.Frame(left_panel, style='Tab.TFrame')
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.wg_btn_exec_file = self.create_button(btn_frame, "▶  Execute (File)", self.wg_execute, 'primary')
        self.wg_btn_exec_file.pack(side=tk.LEFT)
        
        self.wg_btn_exec_copy = self.create_button(btn_frame, "▶📋 Execute (Copy)", self.wg_copy_output, 'primary')
        self.wg_btn_exec_copy.pack(side=tk.LEFT, padx=10)
        
        self.create_button(btn_frame, "Clear", self.wg_clear, 'secondary').pack(side=tk.LEFT)
        
        # === RIGHT PANEL CONTENT (Status) ===
        status_title = tk.Label(right_panel, text="Status / Results", font=FONTS['heading'],
                               bg=COLORS['bg_light'], fg=COLORS['accent'])
        status_title.pack(anchor='w', pady=(5, 10))
        
        self.wg_status_frame, self.wg_status = self.create_text_widget(right_panel, 20)
        self.wg_status_frame.pack(fill=tk.BOTH, expand=True)
        self.wg_status.configure(state='disabled', bg=COLORS['bg_light'])
        
        # Copy button
        copy_btn = self.create_button(right_panel, "📋 Copy to Clipboard", self.wg_copy_status, 'secondary')
        copy_btn.pack(anchor='e', pady=(10, 0))
    
    def wg_clear(self):
        """Clear all inputs."""
        self.wg_input_text.delete('1.0', tk.END)
        self.wg_jira.delete(0, tk.END)
        self.wg_description.delete(0, tk.END)
        self.wg_status.configure(state='normal')
        self.wg_status.delete('1.0', tk.END)
        self.wg_status.configure(state='disabled')
    
    def wg_copy_status(self):
        """Copy status text to clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.wg_status.get('1.0', tk.END))
        messagebox.showinfo("Copied", "Status copied to clipboard")
        
    def _wg_toggle_buttons(self, state):
        """Enable or disable the WG execution buttons during processing."""
        self.wg_btn_exec_file.configure(state=state)
        self.wg_btn_exec_copy.configure(state=state)
        self.root.update()

    def wg_copy_output(self):
        """Process SQL and copy the generated content to clipboard (no files created)."""
        jira_id = self.wg_jira.get().strip()
        description = self.wg_description.get().strip()
        developer = self.wg_developer.get().strip()
        temp_prefix = self.wg_temp_prefix.get().strip()
        raw_text = self.wg_input_text.get('1.0', tk.END).strip()

        if not raw_text:
            messagebox.showerror("Error", "Please paste SQL content")
            return

        # Show processing status
        self.wg_status.configure(state='normal')
        self.wg_status.delete('1.0', tk.END)

        self._wg_toggle_buttons(tk.DISABLED)
        try:
            wg_logic = self._get_logic_module(FEATURE_WORKFILE_GENERATOR)
            results = wg_logic.process_pasted_content_to_clipboard(
                raw_text, jira_id, developer, temp_prefix, description
            )

            if results['errors'] and not results['content']:
                # All objects failed
                self.wg_status.insert(tk.END, "✗ Processing failed:\n")
                for error in results['errors']:
                    self.wg_status.insert(tk.END, f"  • {error}\n")
                self.wg_status.configure(state='disabled')
                return

            # Copy generated SQL to clipboard
            self.root.clipboard_clear()
            self.root.clipboard_append(results['content'])

            # Display summary in status pane
            self.wg_status.insert(tk.END, "═══════════════════════════════════════\n")
            self.wg_status.insert(tk.END, "  COPIED TO CLIPBOARD\n")
            self.wg_status.insert(tk.END, "═══════════════════════════════════════\n\n")
            self.wg_status.insert(tk.END, f"✓ {len(results['processed'])} object(s) generated and copied.\n\n")
            for item in results['processed']:
                self.wg_status.insert(tk.END, f"  [{item['type'][:2]}] {item['name']}\n")

            if results['errors']:
                self.wg_status.insert(tk.END, f"\n⚠ ERRORS:\n")
                for error in results['errors']:
                    self.wg_status.insert(tk.END, f"  • {error}\n")

        except Exception as e:
            self.wg_status.insert(tk.END, f"✗ Error: {str(e)}\n")
        finally:
            self.wg_status.configure(state='disabled')
            self._wg_toggle_buttons(tk.NORMAL)
    
    def wg_execute(self):
        """Execute workfile generation."""
        base_folder = self.wg_base_folder.get().strip()
        jira_id = self.wg_jira.get().strip()
        description = self.wg_description.get().strip()
        developer = self.wg_developer.get().strip()
        temp_prefix = self.wg_temp_prefix.get().strip()
        raw_text = self.wg_input_text.get('1.0', tk.END).strip()
        
        if not base_folder:
            messagebox.showerror("Error", "Please select a base folder")
            return
        
        if not jira_id and self.wg_create_jira_folder.get():
            messagebox.showerror("Error", "Please enter a JIRA number (required when creating JIRA folder)")
            return
        
        if not raw_text:
            messagebox.showerror("Error", "Please paste SQL content")
            return
        
        self.wg_status.configure(state='normal')
        self.wg_status.delete('1.0', tk.END)
        
        self._wg_toggle_buttons(tk.DISABLED)
        try:
            wg_logic = self._get_logic_module(FEATURE_WORKFILE_GENERATOR)
            create_jira_folder = self.wg_create_jira_folder.get()
            results = wg_logic.process_pasted_content(
                raw_text, jira_id, base_folder, developer, temp_prefix, description,
                create_jira_folder_flag=create_jira_folder
            )
            
            # Display results
            self.wg_status.insert(tk.END, f"═══════════════════════════════════════\n")
            self.wg_status.insert(tk.END, f"  PROCESSING COMPLETE\n")
            self.wg_status.insert(tk.END, f"═══════════════════════════════════════\n\n")
            
            if create_jira_folder:
                folder_action = "Created" if results['folder_created'] else "Found existing"
                self.wg_status.insert(tk.END, f"✓ {folder_action} folder:\n")
            else:
                self.wg_status.insert(tk.END, f"✓ Output folder:\n")
            self.wg_status.insert(tk.END, f"  {os.path.basename(results['folder_path'])}\n\n")
            
            # Count by type
            type_counts = {}
            for item in results['processed']:
                obj_type = item.get('type', 'unknown')
                type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
            
            self.wg_status.insert(tk.END, f"Summary:\n")
            for obj_type, count in type_counts.items():
                self.wg_status.insert(tk.END, f"  • {obj_type}: {count}\n")
            self.wg_status.insert(tk.END, f"\nFiles created:\n")
            
            for item in results['processed']:
                name = item.get('name', 'unknown')
                sql_type = item.get('type', 'unknown')
                main_file = item.get('main_file', 'unknown')
                self.wg_status.insert(tk.END, f"  [{sql_type[:2]}] {main_file}\n")
            
            if results['errors']:
                self.wg_status.insert(tk.END, f"\n⚠ ERRORS:\n")
                for error in results['errors']:
                    self.wg_status.insert(tk.END, f"  • {error}\n")
                    
        except Exception as e:
            self.wg_status.insert(tk.END, f"✗ Error: {str(e)}\n")
        finally:
            self.wg_status.configure(state='disabled')
            self._wg_toggle_buttons(tk.NORMAL)
    
    # ========================================================================
    # TAB 4: MULTI-SCHEMA COMBINER
    # ========================================================================
    def create_multi_schema_tab(self, tab=None, add_to_notebook=True):
        """Create the Multi-Schema Combiner tab."""
        tab = self._resolve_tab_container(FEATURE_MULTI_SCHEMA, tab, add_to_notebook)

        main_container = ttk.Frame(tab, style='Tab.TFrame')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel (scrollable to avoid cropping bottom action buttons)
        left_shell = ttk.Frame(main_container, style='Tab.TFrame')
        left_shell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_canvas = tk.Canvas(
            left_shell,
            bg=COLORS['bg'],
            highlightthickness=0,
            bd=0
        )
        left_scrollbar = ttk.Scrollbar(left_shell, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(left_canvas, style='Tab.TFrame')
        left_canvas_window = left_canvas.create_window((0, 0), window=left_panel, anchor='nw')

        def _ms_update_scrollregion(_event=None):
            left_canvas.configure(scrollregion=left_canvas.bbox('all'))

        def _ms_match_canvas_width(event):
            left_canvas.itemconfigure(left_canvas_window, width=event.width)

        left_panel.bind('<Configure>', _ms_update_scrollregion)
        left_canvas.bind('<Configure>', _ms_match_canvas_width)

        # Right panel (status)
        right_panel = ttk.Frame(main_container, style='Status.TFrame')
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(15, 0), ipadx=10, ipady=10)
        right_panel.configure(width=350)
        right_panel.pack_propagate(False)

        # === LEFT PANEL ===

        # --- Input source ---
        src_frame = ttk.LabelFrame(left_panel, text=' Input Source ', style='TLabelframe')
        src_frame.pack(fill=tk.X, pady=(0, 8))
        src_inner = ttk.Frame(src_frame, style='Tab.TFrame')
        src_inner.pack(fill=tk.BOTH, padx=10, pady=8)

        # Source mode selector
        mode_row = ttk.Frame(src_inner, style='Tab.TFrame')
        mode_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(mode_row, text='Source Mode:', style='TLabel', width=14).pack(side=tk.LEFT)
        self.ms_source_mode = tk.StringVar(value='paste')
        ttk.Radiobutton(
            mode_row,
            text='Paste SQL',
            variable=self.ms_source_mode,
            value='paste',
            command=self.ms_toggle_source_mode
        ).pack(side=tk.LEFT, padx=(5, 8))
        ttk.Radiobutton(
            mode_row,
            text='Select Files',
            variable=self.ms_source_mode,
            value='files',
            command=self.ms_toggle_source_mode
        ).pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(
            mode_row,
            text='Input Folder',
            variable=self.ms_source_mode,
            value='folder',
            command=self.ms_toggle_source_mode
        ).pack(side=tk.LEFT, padx=8)

        # Source mode content frames
        self.ms_source_content = ttk.Frame(src_inner, style='Tab.TFrame')
        self.ms_source_content.pack(fill=tk.BOTH, expand=True)

        # Paste mode frame
        self.ms_paste_frame = ttk.Frame(self.ms_source_content, style='Tab.TFrame')
        ttk.Label(self.ms_paste_frame, text='Paste SQL:', style='TLabel').pack(anchor='w')
        self.ms_input_text_frame, self.ms_input_text = self.create_text_widget(self.ms_paste_frame, 5)
        self.ms_input_text_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # Files mode frame
        self.ms_files_mode_frame = ttk.Frame(self.ms_source_content, style='Tab.TFrame')
        files_row = ttk.Frame(self.ms_files_mode_frame, style='Tab.TFrame')
        files_row.pack(fill=tk.X, pady=2)
        ttk.Label(files_row, text='Select Files:', style='TLabel', width=14).pack(side=tk.LEFT)
        self.ms_selected_files = []
        self.ms_files_label = ttk.Label(files_row, text='No files selected', style='TLabel')
        self.ms_files_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.create_button(files_row, 'Select Files', self.ms_browse_files, 'secondary').pack(side=tk.LEFT)
        self.create_button(files_row, 'Clear', self.ms_clear_files, 'secondary').pack(side=tk.LEFT, padx=(5, 0))

        # Folder mode frame
        self.ms_folder_mode_frame = ttk.Frame(self.ms_source_content, style='Tab.TFrame')
        folder_row = ttk.Frame(self.ms_folder_mode_frame, style='Tab.TFrame')
        folder_row.pack(fill=tk.X, pady=2)
        ttk.Label(folder_row, text='Input Folder:', style='TLabel', width=14).pack(side=tk.LEFT)
        self.ms_input_folder_frame, self.ms_input_folder = self.create_entry_widget(folder_row, 38)
        self.ms_input_folder_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.create_button(folder_row, 'Browse', lambda: self.browse_folder(self.ms_input_folder), 'secondary').pack(side=tk.LEFT)

        self.ms_toggle_source_mode()

        # --- Schema selection (checkboxes) ---
        schema_frame = ttk.LabelFrame(left_panel, text=' Target Schemas ', style='TLabelframe')
        schema_frame.pack(fill=tk.X, pady=(0, 8))
        schema_inner = ttk.Frame(schema_frame, style='Tab.TFrame')
        schema_inner.pack(fill=tk.X, padx=10, pady=8)

        # Checkbox grid for schemas
        self.ms_schema_vars = {}  # {schema_name: BooleanVar}
        self.ms_schema_checks_frame = ttk.Frame(schema_inner, style='Tab.TFrame')
        self.ms_schema_checks_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Create checkboxes for default schemas (all checked), 2 per row
        ms_logic = self._get_logic_module(FEATURE_MULTI_SCHEMA)
        for idx, schema in enumerate(ms_logic.DEFAULT_SCHEMAS):
            var = tk.BooleanVar(value=True)
            self.ms_schema_vars[schema] = var
            cb = ttk.Checkbutton(self.ms_schema_checks_frame, text=schema, variable=var)
            cb.grid(row=idx // 2, column=idx % 2, sticky='w', padx=(0, 20), pady=2)

        # Buttons beside checkboxes
        btn_col = ttk.Frame(schema_inner, style='Tab.TFrame')
        btn_col.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        self.create_button(btn_col, 'All', self.ms_select_all_schemas, 'secondary').pack(fill=tk.X, pady=(0, 4))
        self.create_button(btn_col, 'None', self.ms_deselect_all_schemas, 'secondary').pack(fill=tk.X, pady=(0, 8))

        # Add custom schema
        add_row = ttk.Frame(btn_col, style='Tab.TFrame')
        add_row.pack(fill=tk.X)
        ttk.Label(add_row, text='Add:', style='TLabel').pack(anchor='w')
        self.ms_custom_schema_frame, self.ms_custom_schema = self.create_entry_widget(add_row, 16)
        self.ms_custom_schema_frame.pack(fill=tk.X, pady=(2, 4))
        self.create_button(add_row, '+ Add', self.ms_add_custom_schema, 'secondary').pack(fill=tk.X)

        # --- Output options ---
        out_frame = ttk.LabelFrame(left_panel, text=' Output ', style='TLabelframe')
        out_frame.pack(fill=tk.X, pady=(0, 8))
        out_inner = ttk.Frame(out_frame, style='Tab.TFrame')
        out_inner.pack(fill=tk.X, padx=10, pady=8)

        # Output folder
        out_row = ttk.Frame(out_inner, style='Tab.TFrame')
        out_row.pack(fill=tk.X, pady=3)
        ttk.Label(out_row, text='Output Folder:', style='TLabel', width=16).pack(side=tk.LEFT)
        self.ms_output_folder_frame, self.ms_output_folder = self.create_entry_widget(out_row, 35)
        self.ms_output_folder_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.create_button(out_row, 'Browse', lambda: self.browse_folder(self.ms_output_folder), 'secondary').pack(side=tk.LEFT)

        # Output filename
        fn_row = ttk.Frame(out_inner, style='Tab.TFrame')
        fn_row.pack(fill=tk.X, pady=3)
        ttk.Label(fn_row, text='Filename:', style='TLabel', width=16).pack(side=tk.LEFT)
        self.ms_filename_frame, self.ms_filename = self.create_entry_widget(fn_row, 35)
        self.ms_filename.insert(0, f"{datetime.now().strftime('%Y%m%d')} Multi-Schema Combined.sql")
        self.ms_filename_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(fn_row, text='(editable)', style='TLabel', foreground=COLORS['fg_dim']).pack(side=tk.LEFT)

        # Execute buttons
        btn_frame = ttk.Frame(left_panel, style='Tab.TFrame')
        btn_frame.pack(fill=tk.X, pady=8)
        
        self.ms_btn_exec_file = self.create_button(btn_frame, '▶  Execute (File)', self.ms_execute, 'primary')
        self.ms_btn_exec_file.pack(side=tk.LEFT)
        
        self.ms_btn_exec_copy = self.create_button(btn_frame, '▶📋 Execute (Copy)', self.ms_copy_output, 'primary')
        self.ms_btn_exec_copy.pack(side=tk.LEFT, padx=10)
        
        self.create_button(btn_frame, 'Clear All', self.ms_clear, 'secondary').pack(side=tk.LEFT)

        # === RIGHT PANEL ===
        status_title = tk.Label(right_panel, text='Status / Results', font=FONTS['heading'],
                                bg=COLORS['bg_light'], fg=COLORS['accent'])
        status_title.pack(anchor='w', pady=(5, 10))

        self.ms_status_frame, self.ms_status = self.create_text_widget(right_panel, 20)
        self.ms_status_frame.pack(fill=tk.BOTH, expand=True)
        self.ms_status.configure(state='disabled', bg=COLORS['bg_light'])

        copy_btn = self.create_button(right_panel, '📋 Copy to Clipboard', self.ms_copy_status, 'secondary')
        copy_btn.pack(anchor='e', pady=(10, 0))

    def ms_browse_files(self):
        """Open file browser for multiple SQL files."""
        files = filedialog.askopenfilenames(
            title='Select SQL Workfiles',
            filetypes=[('SQL Files', '*.sql'), ('All Files', '*.*')]
        )
        if files:
            self.ms_selected_files = list(files)
            if len(files) == 1:
                self.ms_files_label.configure(text=os.path.basename(files[0]))
            else:
                self.ms_files_label.configure(text=f'{len(files)} files selected')

    def ms_toggle_source_mode(self):
        """Show the selected multi-schema input source frame."""
        self.ms_paste_frame.pack_forget()
        self.ms_files_mode_frame.pack_forget()
        self.ms_folder_mode_frame.pack_forget()

        mode = self.ms_source_mode.get()
        if mode == 'paste':
            self.ms_paste_frame.pack(fill=tk.BOTH, expand=True)
        elif mode == 'files':
            self.ms_files_mode_frame.pack(fill=tk.X)
        else:
            self.ms_folder_mode_frame.pack(fill=tk.X)

    def ms_clear_files(self):
        """Clear selected files."""
        self.ms_selected_files = []
        self.ms_files_label.configure(text='No files selected')

    def ms_select_all_schemas(self):
        """Check all schema checkboxes."""
        for var in self.ms_schema_vars.values():
            var.set(True)

    def ms_deselect_all_schemas(self):
        """Uncheck all schema checkboxes."""
        for var in self.ms_schema_vars.values():
            var.set(False)

    def ms_add_custom_schema(self):
        """Add a custom schema checkbox and check it."""
        name = self.ms_custom_schema.get().strip()
        if not name:
            return
        # Avoid duplicates
        if name not in self.ms_schema_vars:
            var = tk.BooleanVar(value=True)
            self.ms_schema_vars[name] = var
            row_count = len(self.ms_schema_vars) - 1
            cb = ttk.Checkbutton(self.ms_schema_checks_frame, text=name, variable=var)
            cb.grid(row=row_count // 2, column=row_count % 2, sticky='w', padx=(0, 20), pady=2)
        else:
            self.ms_schema_vars[name].set(True)
        self.ms_custom_schema.delete(0, tk.END)

    def ms_clear(self):
        """Clear all inputs and status."""
        self.ms_input_text.delete('1.0', tk.END)
        self.ms_clear_files()
        self.ms_input_folder.delete(0, tk.END)
        self.ms_source_mode.set('paste')
        self.ms_toggle_source_mode()
        self.ms_output_folder.delete(0, tk.END)
        self.ms_filename.delete(0, tk.END)
        self.ms_filename.insert(0, f"{datetime.now().strftime('%Y%m%d')} Multi-Schema Combined.sql")
        self.ms_status.configure(state='normal')
        self.ms_status.delete('1.0', tk.END)
        self.ms_status.configure(state='disabled')

    def ms_copy_status(self):
        """Copy status text to clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.ms_status.get('1.0', tk.END))
        messagebox.showinfo('Copied', 'Status copied to clipboard')

    def _ms_toggle_buttons(self, state):
        """Enable or disable the MS execution buttons during processing."""
        self.ms_btn_exec_file.configure(state=state)
        self.ms_btn_exec_copy.configure(state=state)
        self.root.update()

    def ms_copy_output(self):
        """Build the combined SQL in-memory and copy it to clipboard (no file written)."""
        ms_logic = self._get_logic_module(FEATURE_MULTI_SCHEMA)
        selected_schemas = [name for name, var in self.ms_schema_vars.items() if var.get()]
        if not selected_schemas:
            messagebox.showerror('Error', 'Please select at least one schema')
            return

        mode = self.ms_source_mode.get()
        file_paths = []
        source_labels = []
        pasted_sql = ''

        if mode == 'paste':
            pasted_sql = self.ms_input_text.get('1.0', tk.END).strip()
            if not pasted_sql:
                messagebox.showerror('Error', 'Please paste SQL content')
                return
            source_labels = ['Pasted SQL']
        elif mode == 'files':
            file_paths = list(self.ms_selected_files)
            if not file_paths:
                messagebox.showerror('Error', 'Please select one or more SQL files')
                return
            source_labels = [os.path.basename(fp) for fp in file_paths]
        else:
            folder = self.ms_input_folder.get().strip()
            if not folder:
                messagebox.showerror('Error', 'Please choose an input folder')
                return
            file_paths = ms_logic.get_sql_files_from_folder(folder)
            if not file_paths:
                messagebox.showerror('Error', 'No .sql files found in the selected folder')
                return
            source_labels = [os.path.basename(fp) for fp in file_paths]

        self.ms_status.configure(state='normal')
        self.ms_status.delete('1.0', tk.END)

        self._ms_toggle_buttons(tk.DISABLED)
        try:
            if mode == 'paste':
                results = ms_logic.combine_text_for_schemas_to_clipboard(
                    pasted_sql, selected_schemas
                )
            else:
                results = ms_logic.combine_for_schemas_to_clipboard(
                    file_paths, selected_schemas
                )

            if results['errors'] and not results['content']:
                self.ms_status.insert(tk.END, '✗ Processing failed:\n')
                for error in results['errors']:
                    self.ms_status.insert(tk.END, f'  • {error}\n')
                self.ms_status.configure(state='disabled')
                return

            # Copy to clipboard
            self.root.clipboard_clear()
            self.root.clipboard_append(results['content'])

            # Show summary in status pane
            self.ms_status.insert(tk.END, '═══════════════════════════════════════\n')
            self.ms_status.insert(tk.END, '  COPIED TO CLIPBOARD\n')
            self.ms_status.insert(tk.END, '═══════════════════════════════════════\n\n')
            self.ms_status.insert(tk.END, f"✓ Files combined : {results['files_processed']}\n")
            self.ms_status.insert(tk.END, f"✓ Schemas        : {len(results['schemas'])}\n")
            self.ms_status.insert(tk.END, f"✓ Total blocks   : {results['files_processed'] * len(results['schemas'])}\n\n")
            self.ms_status.insert(tk.END, 'Schemas included:\n')
            for schema in results['schemas']:
                self.ms_status.insert(tk.END, f'  • {schema}\n')
            self.ms_status.insert(tk.END, '\nSource:\n')
            for label in source_labels:
                self.ms_status.insert(tk.END, f'  • {label}\n')

            if results['errors']:
                self.ms_status.insert(tk.END, '\n⚠ ERRORS:\n')
                for error in results['errors']:
                    self.ms_status.insert(tk.END, f'  • {error}\n')

        except Exception as e:
            self.ms_status.insert(tk.END, f'✗ Error: {str(e)}\n')
        finally:
            self.ms_status.configure(state='disabled')
            self._ms_toggle_buttons(tk.NORMAL)

    def ms_execute(self):
        """Execute multi-schema combination."""
        ms_logic = self._get_logic_module(FEATURE_MULTI_SCHEMA)
        # Collect checked schemas
        selected_schemas = [name for name, var in self.ms_schema_vars.items() if var.get()]

        if not selected_schemas:
            messagebox.showerror('Error', 'Please select at least one schema')
            return

        output_folder = self.ms_output_folder.get().strip()
        if not output_folder:
            messagebox.showerror('Error', 'Please select an output folder')
            return

        filename = self.ms_filename.get().strip()
        if not filename:
            filename = f"{datetime.now().strftime('%Y%m%d')} Multi-Schema Combined.sql"
        if not filename.endswith('.sql'):
            filename += '.sql'

        output_path = os.path.join(output_folder, filename)

        mode = self.ms_source_mode.get()
        file_paths = []
        source_labels = []
        pasted_sql = ''

        if mode == 'paste':
            pasted_sql = self.ms_input_text.get('1.0', tk.END).strip()
            if not pasted_sql:
                messagebox.showerror('Error', 'Please paste SQL content')
                return
            source_labels = ['Pasted SQL']
        elif mode == 'files':
            file_paths = list(self.ms_selected_files)
            if not file_paths:
                messagebox.showerror('Error', 'Please select one or more SQL files')
                return
            source_labels = [os.path.basename(fp) for fp in file_paths]
        else:
            folder = self.ms_input_folder.get().strip()
            if not folder:
                messagebox.showerror('Error', 'Please choose an input folder')
                return
            file_paths = ms_logic.get_sql_files_from_folder(folder)
            if not file_paths:
                messagebox.showerror('Error', 'No .sql files found in the selected folder')
                return
            source_labels = [os.path.basename(fp) for fp in file_paths]

        self.ms_status.configure(state='normal')
        self.ms_status.delete('1.0', tk.END)

        self._ms_toggle_buttons(tk.DISABLED)
        try:
            if mode == 'paste':
                results = ms_logic.combine_text_for_schemas(
                    pasted_sql, selected_schemas, output_path
                )
            else:
                results = ms_logic.combine_for_schemas(
                    file_paths, selected_schemas, output_path
                )

            self.ms_status.insert(tk.END, '═══════════════════════════════════════\n')
            self.ms_status.insert(tk.END, '  MULTI-SCHEMA COMBINATION COMPLETE\n')
            self.ms_status.insert(tk.END, '═══════════════════════════════════════\n\n')

            self.ms_status.insert(tk.END, f"✓ Files combined : {results['files_processed']}\n")
            self.ms_status.insert(tk.END, f"✓ Schemas        : {len(results['schemas'])}\n")
            self.ms_status.insert(tk.END, f"✓ Total blocks   : {results['files_processed'] * len(results['schemas'])}\n\n")

            self.ms_status.insert(tk.END, 'Schemas included:\n')
            for schema in results['schemas']:
                self.ms_status.insert(tk.END, f'  • {schema}\n')

            self.ms_status.insert(tk.END, '\nSource:\n')
            for label in source_labels:
                self.ms_status.insert(tk.END, f'  • {label}\n')

            if results['output_file']:
                self.ms_status.insert(tk.END, f"\n✓ Output saved to:\n  {results['output_file']}\n")

            if results['errors']:
                self.ms_status.insert(tk.END, '\n⚠ ERRORS:\n')
                for error in results['errors']:
                    self.ms_status.insert(tk.END, f'  • {error}\n')

        except Exception as e:
            self.ms_status.insert(tk.END, f'✗ Error: {str(e)}\n')
        finally:
            self.ms_status.configure(state='disabled')
            self._ms_toggle_buttons(tk.NORMAL)

    # ========================================================================
    # FOOTER
    # ========================================================================
    def create_footer(self):
        """Create footer with author information."""
        footer = ttk.Frame(self.main_frame, style='Main.TFrame')
        footer.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        author_label = tk.Label(
            footer,
            text="Author: Abhinav Prasad",
            font=FONTS['footer'],
            bg=COLORS['bg'],
            fg=COLORS['fg_dim']
        )
        author_label.pack(side=tk.RIGHT)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def main():
    root = tk.Tk()
    app = SQLToolsApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
