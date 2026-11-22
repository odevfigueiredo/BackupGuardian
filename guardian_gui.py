#!/usr/bin/env python3
"""Painel offline para criação, verificação, recuperação e proteção de backups."""

from collections import deque
from datetime import datetime
from pathlib import Path
from queue import Empty, SimpleQueue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import backup_guardian as guardian
import guardian_theme as theme


def short_path(path, limit=76):
    text = str(path)
    if len(text) <= limit:
        return text
    return f'{text[:22]}…{text[-(limit - 23):]}'


def date_label(timestamp):
    try:
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return parsed.astimezone().strftime('%d/%m/%Y · %H:%M')
    except (ValueError, OverflowError, OSError):
        return '—'


class BackupGuardianApp:
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.vault = None
        self.catalog = []
        self.checks = {}
        self.events = deque(maxlen=100)
        self.page = None
        self.selected_path = None
        self.pending_snapshot = None
        self.fonts = theme.configure(root)
        root.title('Backup Guardian')
        root.geometry('1160x772')
        root.minsize(880, 660)
        root.configure(bg=theme.BG)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Control-n>', self._shortcut_new)
        root.bind('<F5>', self._shortcut_refresh)

        self._sidebar()
        top = tk.Frame(root, bg=theme.PAPER, padx=26, pady=15)
        top.grid(row=0, column=1, sticky='ew')
        self.breadcrumb = tk.StringVar(root)
        self.label(top, variable=self.breadcrumb, font='bold').pack(side='left')
        tk.Label(top, text='●  Offline', bg='#e4f4ed', fg=theme.GOOD, font=self.fonts['bold'],
                 padx=11, pady=3).pack(side='right')

        self.workspace = tk.Frame(root, bg=theme.BG, padx=26, pady=18)
        self.workspace.grid(row=1, column=1, sticky='nsew')
        root.bind('<MouseWheel>', self._wheel, add='+')
        root.bind('<Button-4>', self._wheel, add='+')
        root.bind('<Button-5>', self._wheel, add='+')
        root.bind('<FocusIn>', self._reveal_focus, add='+')
        footer = tk.Frame(root, bg=theme.PAPER, padx=26, pady=10)
        footer.grid(row=2, column=1, sticky='ew')
        self.status = tk.StringVar(root, value='Pronto')
        self.label(footer, variable=self.status, color=theme.MUTED, font='small').pack(side='left', fill='x', expand=True)
        self.progress = ttk.Progressbar(footer, mode='indeterminate', length=116,
                                       style='Guardian.Horizontal.TProgressbar')
        self.show_backups()

    def label(self, parent, text='', *, variable=None, color=theme.INK, font='body', **kwargs):
        return tk.Label(parent, text=text, textvariable=variable, bg=parent.cget('bg'), fg=color,
                        font=self.fonts[font], anchor='w', justify='left', **kwargs)

    def button(self, parent, text, action, style='Secondary'):
        button = ttk.Button(parent, text=text, command=action, style=f'{style}.TButton')
        def activate(_event):
            button.invoke()
            return 'break'

        button.bind('<Return>', activate)
        return button

    def card(self, parent, *, background=theme.PAPER, border=theme.LINE, padding=17):
        return tk.Frame(parent, bg=background, padx=padding, pady=padding,
                        highlightbackground=border, highlightthickness=1)

    def _sidebar(self):
        side = tk.Frame(self.root, bg=theme.NAV, width=214, padx=16, pady=21)
        side.grid(row=0, column=0, rowspan=3, sticky='ns')
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=theme.NAV)
        brand.pack(fill='x', pady=(2, 35))
        icon = tk.Canvas(brand, width=37, height=37, bg='#2a57d4', highlightthickness=0)
        icon.pack(side='left', padx=(0, 10))
        icon.create_polygon(18, 7, 28, 11, 27, 21, 24, 26, 18, 30, 12, 26, 9, 21, 8, 11,
                            fill='', outline='#e2ecff', width=2)
        icon.create_line(13, 18, 17, 22, 24, 14, fill='#8cebd6', width=2)
        labels = tk.Frame(brand, bg=theme.NAV)
        labels.pack(side='left')
        self.label(labels, 'Backup Guardian', color=theme.PAPER, font='bold').pack(anchor='w')
        self.label(labels, 'Cópias e recuperação', color=theme.NAV_TEXT, font='small').pack(anchor='w', pady=(2, 0))

        self.nav = {}
        for name, title, action in (
            ('backups', '▤   Backups', self.show_backups),
            ('crypto', '◇   Criptografia', self.show_crypto),
            ('activity', '◷   Atividade', self.show_activity),
        ):
            control = self.button(side, title, action, 'Nav')
            control.pack(fill='x', pady=(0, 7))
            self.nav[name] = control
        self.label(side, f'Backup Guardian {guardian.VERSION}', color=theme.NAV_TEXT, font='small').pack(
            side='bottom', anchor='w'
        )

    def _shortcut_new(self, _event):
        if not self.busy and self.page == 'backups':
            self.show_create()

    def _shortcut_refresh(self, _event):
        if not self.busy and self.page == 'backups' and self.vault:
            self.load_vault(self.vault)

    def close(self):
        if self.busy:
            self.root.bell()
        else:
            self.root.destroy()

    def _screen(self, name, crumb, title, description, *, back=False, action=None):
        self.page = name
        self.breadcrumb.set(crumb)
        active = 'backups' if name in ('create', 'verify', 'restore') else name
        for key, control in self.nav.items():
            control.configure(style='Current.TButton' if key == active else 'Nav.TButton')
        for widget in self.workspace.winfo_children():
            widget.destroy()
        self.content = self._scrollable_page(fill_viewport=name in ('backups', 'activity'))

        header = tk.Frame(self.content, bg=theme.BG)
        header.pack(fill='x', pady=(0, 15))
        if back:
            self.button(header, '← Backups', self.show_backups).pack(anchor='w', pady=(0, 9))
        if action:
            text, callback = action
            self.button(header, text, callback, 'Primary').pack(side='right', anchor='n', pady=(4, 0))
        self.label(header, title, font='title').pack(anchor='w')
        description = self.label(header, description, color=theme.MUTED)
        description.pack(fill='x', pady=(2, 0))
        self._wrap(description)

    def _scrollable_page(self, *, fill_viewport):
        frame = tk.Frame(self.workspace, bg=theme.BG)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        canvas = self.canvas = tk.Canvas(frame, bg=theme.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview,
                                  style='Guardian.Vertical.TScrollbar', takefocus=False)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        frame.columnconfigure(1, minsize=scrollbar.winfo_reqwidth())
        content = tk.Frame(canvas, bg=theme.BG)
        panel = canvas.create_window(0, 0, window=content, anchor='nw')

        def arrange(_event):
            width = max(canvas.winfo_width(), 1)
            height = content.winfo_reqheight()
            if fill_viewport:
                height = max(height, canvas.winfo_height())
                canvas.itemconfigure(panel, width=width, height=height)
            else:
                canvas.itemconfigure(panel, width=width)
            canvas.configure(scrollregion=(0, 0, width, height))
            if height > canvas.winfo_height():
                scrollbar.grid()
            else:
                scrollbar.grid_remove()

        canvas.bind('<Configure>', arrange)
        content.bind('<Configure>', arrange)
        self.root.after_idle(lambda: canvas.winfo_exists() and arrange(None))
        return content

    def _belongs_to_page(self, widget):
        while widget is not None:
            if widget in (self.content, self.canvas):
                return True
            widget = getattr(widget, 'master', None)
        return False

    def _wheel(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if isinstance(widget, (tk.Text, ttk.Treeview)) or not self._belongs_to_page(widget):
            return
        increment = -1 if event.num == 4 or event.delta > 0 else 1
        self.canvas.yview_scroll(increment * 3, 'units')

    def _reveal_focus(self, event):
        widget = event.widget
        if not isinstance(widget, (ttk.Entry, ttk.Button, ttk.Treeview, tk.Text)) or not self._belongs_to_page(widget):
            return
        relative = widget.winfo_rooty() - self.canvas.winfo_rooty()
        top_in_page = widget.winfo_rooty() - self.content.winfo_rooty()
        viewport = self.canvas.winfo_height()
        if relative < 0:
            offset = top_in_page - 8
        elif relative + widget.winfo_height() > viewport:
            offset = top_in_page + widget.winfo_height() - viewport + 8
        else:
            return
        self.canvas.yview_moveto(max(offset, 0) / max(self.content.winfo_height(), 1))

    def _wrap(self, widget):
        widget.bind('<Configure>', lambda event: widget.configure(wraplength=max(event.width - 4, 120)))

    def _set_busy(self, busy):
        self.busy = busy
        if busy:
            self.disabled = []

            def disable_children(parent):
                for child in parent.winfo_children():
                    if isinstance(child, (ttk.Button, ttk.Entry)) and not child.instate(['disabled']):
                        child.state(['disabled'])
                        self.disabled.append(child)
                    disable_children(child)

            disable_children(self.root)
            self.progress.pack(side='right', padx=(12, 0))
            self.progress.start(13)
        else:
            self.progress.stop()
            self.progress.pack_forget()
            for child in self.disabled:
                if child.winfo_exists():
                    child.state(['!disabled'])
            if self.page == 'backups':
                self._selection()

    def _run(self, label, operation, success, failure, *, record=True):
        if self.busy:
            return
        self._set_busy(True)
        self.status.set(label + '…')
        result = SimpleQueue()

        def work():
            try:
                result.put((True, operation()))
            except Exception as error:
                result.put((False, str(error) or type(error).__name__))

        def poll():
            try:
                ok, value = result.get_nowait()
            except Empty:
                self.root.after(50, poll)
                return
            self._set_busy(False)
            if ok:
                success(value)
            else:
                if record:
                    self._event(label, 'Falha')
                self.status.set('A operação encontrou um problema')
                failure(value)

        try:
            threading.Thread(target=work).start()
        except RuntimeError as error:
            result.put((False, str(error)))
        self.root.after(50, poll)

    def _event(self, operation, result):
        self.events.appendleft((datetime.now().strftime('%H:%M:%S'), operation, result))
        self.status.set(f'Última operação   {operation} · {result}')

    def _table(self, parent, columns, specs):
        frame = tk.Frame(parent, bg=theme.PAPER)
        frame.pack(fill='both', expand=True)
        bar = ttk.Scrollbar(frame, orient='vertical', style='Guardian.Vertical.TScrollbar', takefocus=False)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse',
                            height=3, style='Guardian.Treeview', yscrollcommand=bar.set)
        bar.configure(command=tree.yview)
        bar.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        for name, (title, width, stretch) in zip(columns, specs):
            tree.heading(name, text=title, anchor='w')
            tree.column(name, width=width, minwidth=min(90, width), stretch=stretch, anchor='w')
        tree.tag_configure('alternate', background='#f6f8fd')
        tree.tag_configure('good', foreground=theme.GOOD)
        tree.tag_configure('bad', foreground=theme.BAD)
        return tree

    def _health(self, item):
        if item['error']:
            return 'Manifesto com erro', 'bad'
        check = self.checks.get(item['path'])
        if check is None:
            return 'Não verificado', ''
        return ('Íntegro', 'good') if check else ('Com falhas', 'bad')

    def show_backups(self):
        pending = self.pending_snapshot
        self._render_backups(pending or self.selected_path)
        if pending is not None:
            self.load_vault(pending.parent.parent, selected=pending, reset_checks=False)

    def _render_backups(self, selected=None):
        self._screen('backups', 'Armazenamento local  /  Backups', 'Backups',
                     'Crie, verifique e restaure cópias dos seus arquivos.',
                     action=('+  Novo backup', self.show_create))
        title = (self.vault.name or self.vault.anchor) if self.vault else 'Nenhuma pasta selecionada'
        location = short_path(self.vault, 49) if self.vault else ''
        banner = theme.VaultBanner(
            self.content, self.fonts,
            lambda parent: self.button(parent, 'Escolher pasta…', self.choose_vault), title, location
        )
        banner.pack(fill='x')

        metric_row = tk.Frame(self.content, bg=theme.BG)
        metric_row.pack(fill='x', pady=12)
        self.metrics = []
        for column, (title, color) in enumerate((
            ('Snapshots', theme.INK), ('Íntegros na sessão', theme.GOOD), ('Com alertas', theme.BAD),
        )):
            metric_row.columnconfigure(column, weight=1, uniform='metrics')
            card = self.card(metric_row, padding=10)
            card.grid(row=0, column=column, sticky='ew', padx=(0 if column == 0 else 6, 6 if column < 2 else 0))
            value = self.label(card, '0', color=color, font='metric')
            value.pack(anchor='w')
            self.label(card, title, color=theme.MUTED, font='small').pack(anchor='w')
            self.metrics.append(value)

        catalog_card = self.card(self.content, padding=12)
        catalog_card.pack(fill='both', expand=True)
        toolbar = tk.Frame(catalog_card, bg=theme.PAPER)
        toolbar.pack(fill='x', pady=(0, 8))
        self.label(toolbar, 'Snapshots disponíveis', font='section').pack(side='left')
        self.button(toolbar, 'Abrir snapshot…', self.open_snapshot).pack(side='right')
        self.refresh = self.button(toolbar, 'Atualizar', lambda: self.load_vault(self.vault))
        self.refresh.pack(side='right', padx=(0, 7))
        if self.vault is None:
            self.refresh.state(['disabled'])
        self.catalog_hint = self.label(catalog_card, color=theme.MUTED, font='small')
        self.catalog_hint.pack(fill='x', pady=(0, 8))
        self.tree = self._table(catalog_card, ('source', 'date', 'files', 'status'), (
            ('Origem', 200, True), ('Criado em', 150, True), ('Arquivos', 76, False), ('Última checagem', 146, True)
        ))
        self.tree.bind('<<TreeviewSelect>>', self._selection)
        action_row = tk.Frame(catalog_card, bg=theme.PAPER)
        action_row.pack(fill='x', pady=(9, 0))
        self.detail = self.label(action_row, color=theme.MUTED, font='small')
        self.detail.pack(side='left', anchor='w', fill='x', expand=True)
        self.restore_button = self.button(action_row, 'Restaurar…', self.restore_selected)
        self.restore_button.pack(side='right')
        self.verify_button = self.button(action_row, 'Verificar', self.verify_selected)
        self.verify_button.pack(side='right', padx=(0, 7))
        self._populate(selected)

    def _populate(self, selected):
        statuses = [self._health(item) for item in self.catalog]
        counts = (len(statuses), sum(tag == 'good' for _, tag in statuses), sum(tag == 'bad' for _, tag in statuses))
        for label, count in zip(self.metrics, counts):
            label.configure(text=str(count))
        if self.vault is None:
            hint = 'Escolha a pasta que contém suas cópias ou crie um backup.'
        elif not self.catalog:
            hint = 'Ainda não há snapshots nesta pasta.'
        else:
            hint = 'Selecione uma cópia para verificar seus arquivos ou restaurá-la.'
        self.catalog_hint.configure(text=hint)
        self.items = {}
        selected_id = None
        for index, (item, (status, tag)) in enumerate(zip(self.catalog, statuses)):
            row = str(index)
            self.items[row] = item
            self.tree.insert('', 'end', iid=row, values=(
                item['source_name'] or item['path'].name, date_label(item['created_utc']),
                '—' if item['error'] else item['files'], status
            ), tags=(('alternate' if index % 2 else ''), tag))
            if item['path'] == selected:
                selected_id = row
        if selected_id is None and self.catalog:
            selected_id = '0'
        if selected_id is not None:
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)
            self.tree.see(selected_id)
        self._selection()

    def _selected(self):
        rows = self.tree.selection()
        return self.items.get(rows[0]) if rows else None

    def _selection(self, _event=None):
        selected = self._selected()
        self.verify_button.state(['!disabled'] if selected and not self.busy else ['disabled'])
        self.restore_button.state(['!disabled'] if selected and not selected['error'] and not self.busy else ['disabled'])
        if selected:
            self.selected_path = selected['path']
        text = f"ID  {short_path(selected['path'].name, 34)}" if selected else 'Nenhum snapshot selecionado'
        self.detail.configure(text=text)

    def choose_vault(self):
        value = filedialog.askdirectory(parent=self.root, title='Escolher pasta de backups', mustexist=True)
        if value:
            self.load_vault(value)

    def load_vault(self, path, *, selected=None, reset_checks=True):
        path = Path(path).expanduser()

        def read_catalog():
            folder = path.resolve(strict=True)
            if not folder.is_dir():
                raise ValueError('Escolha uma pasta de backups.')
            return folder, guardian.snapshot_catalog(folder)

        def loaded(result):
            self.vault, self.catalog = result
            self.pending_snapshot = None
            if reset_checks:
                for item in self.catalog:
                    self.checks.pop(item['path'], None)
            self._render_backups(selected)
            self.status.set(f'{len(self.catalog)} snapshot(s) na pasta selecionada')

        def failed(detail):
            self.catalog_hint.configure(text=f'Não foi possível ler a pasta. {short_path(detail, 94)}', fg=theme.BAD)

        self._run('Lendo pasta de backups', read_catalog, loaded, failed, record=False)

    def open_snapshot(self):
        name = filedialog.askdirectory(parent=self.root, title='Abrir pasta de um snapshot', mustexist=True)
        if name:
            self.show_verify(Path(name))

    def verify_selected(self):
        item = self._selected()
        if item:
            self.show_verify(item['path'])

    def restore_selected(self):
        item = self._selected()
        if item and not item['error']:
            self.show_restore(item['path'])

    def _field(self, parent, title, *, value='', secret=False, browse=None, autofocus=False):
        row = tk.Frame(parent, bg=parent.cget('bg'))
        row.pack(fill='x', pady=(0, 12))
        self.label(row, title, font='bold').pack(anchor='w', pady=(0, 5))
        variable = tk.StringVar(self.root, value=value)
        entry = ttk.Entry(row, textvariable=variable, style='Guardian.TEntry',
                          font=self.fonts['body'], show='•' if secret else '')
        if browse:
            def choose():
                selected = browse()
                if selected:
                    variable.set(selected)

            self.button(row, 'Procurar…', choose).pack(side='right', padx=(8, 0))
        entry.pack(side='left', fill='x', expand=True)
        if autofocus:
            self.root.after_idle(lambda: entry.winfo_exists() and entry.focus_set())
        return variable

    def _panel(self, heading, description):
        panel = self.card(self.content, padding=18)
        panel.pack(fill='x')
        self.label(panel, heading, font='section').pack(anchor='w')
        subtitle = self.label(panel, description, color=theme.MUTED)
        subtitle.pack(fill='x', pady=(3, 16))
        self._wrap(subtitle)
        return panel

    def _result_area(self):
        area = tk.Frame(self.content, bg=theme.BG)
        area.pack(fill='both', expand=True, pady=(12, 0))
        return area

    def _feedback(self, area, title, detail, *, kind='info', problems=()):
        for widget in area.winfo_children():
            widget.destroy()
        background, border, color = {
            'info': ('#f7faff', '#c8d9f6', '#254eaa'),
            'good': ('#edf8f2', '#aedac5', theme.GOOD),
            'bad': ('#fff3f5', '#ebc1ca', theme.BAD),
        }[kind]
        result = self.card(area, background=background, border=border, padding=14)
        result.pack(fill='x')
        self.label(result, title, color=color, font='section').pack(anchor='w')
        body = self.label(result, detail, color=theme.INK)
        body.pack(fill='x', pady=(4, 0))
        self._wrap(body)
        if problems:
            lines = list(problems[:100])
            if len(problems) > 100:
                lines.append(f'Mais {len(problems) - 100} ocorrências.')
            row = tk.Frame(result, bg=background)
            row.pack(fill='x', pady=(8, 0))
            text = tk.Text(row, height=min(len(lines), 5), bg=background, fg=color, relief='flat',
                           wrap='word', font=self.fonts['body'], highlightthickness=1,
                           highlightcolor=color, highlightbackground=border)
            bar = ttk.Scrollbar(row, command=text.yview, style='Guardian.Vertical.TScrollbar', takefocus=False)
            text.configure(yscrollcommand=bar.set)
            bar.pack(side='right', fill='y')
            text.pack(fill='x', expand=True)
            text.insert('1.0', '\n'.join(lines))
            text.configure(state='disabled')

    def _select_folder(self, title):
        return filedialog.askdirectory(parent=self.root, title=title, mustexist=True)

    def show_create(self):
        self._screen('create', 'Backups  /  Novo backup', 'Novo backup',
                     'Escolha o que copiar e onde guardar o snapshot.', back=True)
        form = self._panel('Origem e destino', 'O Backup Guardian confere os arquivos copiados com SHA-256.')
        source = self._field(form, 'Pasta de origem', browse=lambda: self._select_folder('Escolher pasta de origem'), autofocus=True)
        vault = self._field(form, 'Pasta de backups', value=str(self.vault or ''),
                            browse=lambda: self._select_folder('Escolher pasta de backups'))

        def submit():
            origin, destination = source.get(), vault.get()
            if not origin or not destination:
                self._feedback(area, 'Informe as duas pastas', 'Selecione uma origem e uma pasta de backups.', kind='bad')
                return

            def create():
                # A pasta precisa continuar disponível quando a operação começa.
                # Uma mídia desconectada deve causar erro nesta etapa.
                if not Path(destination).expanduser().is_dir():
                    raise ValueError('A pasta de backups está indisponível. Confira a conexão do dispositivo.')
                return guardian.create(origin, destination)

            def created(result):
                path, count = result
                self.checks[path] = True
                self.pending_snapshot = path
                self._event('Criar backup', 'Concluído')
                self._feedback(area, 'Backup criado', f'{count} arquivo(s) conferido(s)\n{path}', kind='good')
                self.button(area, 'Abrir no painel', self.show_backups).pack(anchor='w', pady=(9, 0))

            self._run('Criar backup', create, created,
                      lambda error: self._feedback(area, 'Falha na criação', error, kind='bad'))

        self.button(form, 'Criar backup', submit, 'Primary').pack(anchor='w')
        area = self._result_area()

    def show_verify(self, snapshot):
        self._screen('verify', 'Backups  /  Verificação', 'Verificar backup',
                     'Compare os arquivos da cópia com o manifesto SHA-256.', back=True)
        panel = self._panel('Snapshot selecionado', short_path(snapshot))
        controls = tk.Frame(panel, bg=theme.PAPER)
        controls.pack(fill='x')
        area = self._result_area()

        def start():
            self._feedback(area, 'Verificação em andamento', 'Conferindo arquivos e diretórios do snapshot.')
            self._run('Verificar backup', lambda: guardian.verify(snapshot), verified, failed)

        def verified(report):
            ok = report['ok']
            self.checks[snapshot] = ok
            self._event('Verificar backup', 'Íntegro' if ok else 'Com falhas')
            if ok:
                self._feedback(area, 'Backup íntegro', f'{report["files"]} arquivo(s) conferido(s) com SHA-256.',
                               kind='good')
                self.button(area, 'Restaurar este backup…', lambda: self.show_restore(snapshot)).pack(
                    anchor='w', pady=(9, 0)
                )
            else:
                problems = report['problems']
                self._feedback(area, 'Backup com falhas', f'{len(problems)} ocorrência(s) de integridade.',
                               kind='bad', problems=problems)

        def failed(error):
            self.checks[snapshot] = False
            self._feedback(area, 'Falha na verificação', error, kind='bad')

        self.button(controls, 'Verificar novamente', start).pack(side='left')
        start()

    def show_restore(self, snapshot):
        self._screen('restore', 'Backups  /  Restauração', 'Restaurar backup',
                     'Recupere os arquivos do snapshot em uma nova pasta.', back=True)
        form = self._panel('Destino da restauração', short_path(snapshot))

        def choose_parent():
            parent = self._select_folder('Escolher onde criar a pasta restaurada')
            return str(Path(parent) / f'Restauração-{snapshot.name}') if parent else ''

        destination = self._field(form, 'Caminho da nova pasta', browse=choose_parent, autofocus=True)
        self.label(form, 'Escolha um caminho que ainda não exista.', color=theme.MUTED, font='small').pack(
            anchor='w', pady=(0, 12)
        )

        def submit():
            target = destination.get()
            if not target:
                self._feedback(area, 'Informe um destino', 'Preencha o caminho da nova pasta.', kind='bad')
                return
            self._feedback(area, 'Restauração em andamento', 'Validando o snapshot antes de salvar a cópia.')
            self._run('Restaurar backup', lambda: guardian.restore(snapshot, target), restored,
                      lambda error: self._feedback(area, 'Falha na restauração', error, kind='bad'))

        def restored(result):
            path, count = result
            self.checks[snapshot] = True
            self._event('Restaurar backup', 'Concluído')
            self._feedback(area, 'Backup restaurado', f'{count} arquivo(s) recuperado(s) em\n{path}', kind='good')

        self.button(form, 'Restaurar arquivos', submit, 'Primary').pack(anchor='w')
        area = self._result_area()

    def show_crypto(self, mode='seal'):
        sealing = mode == 'seal'
        self._screen('crypto', 'Armazenamento local  /  Criptografia', 'Criptografia',
                     'Proteja arquivos com senha ou recupere um arquivo .bgc.')
        tabs = tk.Frame(self.content, bg=theme.BG)
        tabs.pack(fill='x', pady=(0, 12))
        for option, title in (('seal', 'Criptografar'), ('unseal', 'Descriptografar')):
            self.button(tabs, title, lambda selected=option: self.show_crypto(selected),
                        'Primary' if mode == option else 'Secondary').pack(side='left', padx=(0, 8))

        heading = 'Criptografar arquivo' if sealing else 'Descriptografar arquivo'
        message = ('Crie uma cópia protegida com AES-256-GCM.'
                   if sealing else 'A integridade é validada antes de salvar o conteúdo recuperado.')
        form = self._panel(heading, message)

        suggestion = None

        def choose_source():
            nonlocal suggestion
            filetypes = [('Todos os arquivos', '*')] if sealing else [('Backup Guardian', '*.bgc'), ('Todos os arquivos', '*')]
            value = filedialog.askopenfilename(parent=self.root, title='Selecionar arquivo de origem', filetypes=filetypes)
            if value and destination.get() in ('', suggestion):
                path = Path(value)
                if sealing:
                    suggested = path.with_name(path.name + '.bgc')
                elif path.suffix.lower() == '.bgc' and path.stem:
                    candidate = path.with_suffix('')
                    suggested = candidate.with_stem(candidate.stem + '-recuperado')
                else:
                    suggested = path.with_name(path.name + '-recuperado')
                suggestion = str(suggested)
                destination.set(suggestion)
            return value

        source = self._field(form, 'Arquivo de origem', browse=choose_source, autofocus=True)
        destination = self._field(
            form, 'Salvar como',
            browse=lambda: filedialog.asksaveasfilename(
                parent=self.root, title='Escolher arquivo de saída', defaultextension='.bgc' if sealing else ''
            )
        )
        password_row = tk.Frame(form, bg=theme.PAPER)
        password_row.pack(fill='x')
        password_column = tk.Frame(password_row, bg=theme.PAPER)
        password_column.pack(side='left', fill='x', expand=True)
        password = self._field(password_column, 'Senha (mínimo de 12 caracteres)', secret=True)
        confirmation = None
        if sealing:
            confirmation_column = tk.Frame(password_row, bg=theme.PAPER)
            confirmation_column.pack(side='left', fill='x', expand=True, padx=(12, 0))
            confirmation = self._field(confirmation_column, 'Confirmar senha', secret=True)
        operation = guardian.seal_file if sealing else guardian.unseal_file

        def submit():
            origin, target = source.get(), destination.get()
            secret = password.get()
            if not origin or not target:
                self._feedback(area, 'Informe os dois arquivos', 'Escolha os caminhos de origem e destino.', kind='bad')
            elif len(secret) < 12:
                self._feedback(area, 'Senha muito curta', 'Use pelo menos 12 caracteres.', kind='bad')
            elif confirmation is not None and secret != confirmation.get():
                self._feedback(area, 'As senhas são diferentes', 'Digite a mesma senha nos dois campos.', kind='bad')
            else:
                password.set('')
                if confirmation is not None:
                    confirmation.set('')

                def completed(path):
                    self._event(heading, 'Concluído')
                    title = 'Arquivo criptografado' if sealing else 'Arquivo recuperado'
                    self._feedback(area, title, str(path), kind='good')

                self._feedback(area, 'Processando arquivo', 'Aguarde a conclusão da operação.')
                self._run(heading, lambda: operation(origin, target, secret), completed,
                          lambda error: self._feedback(area, 'Falha na operação', error, kind='bad'))

        self.button(form, heading, submit, 'Primary').pack(anchor='w')
        area = self._result_area()

    def show_activity(self):
        self._screen('activity', 'Armazenamento local  /  Atividade', 'Atividade',
                     'Veja o resultado das operações desta sessão.')
        panel = self.card(self.content, padding=16)
        panel.pack(fill='both', expand=True)
        self.label(panel, 'Operações recentes', font='section').pack(anchor='w', pady=(0, 10))
        if not self.events:
            self.label(panel, 'As operações aparecerão aqui após o primeiro backup ou verificação.',
                       color=theme.MUTED).pack(anchor='w', pady=(0, 8))
        tree = self._table(panel, ('time', 'operation', 'result'), (
            ('Hora', 100, False), ('Operação', 220, True), ('Resultado', 175, True)
        ))
        for index, entry in enumerate(self.events):
            tag = 'bad' if entry[2] in ('Falha', 'Com falhas') else 'good'
            tree.insert('', 'end', values=entry, tags=(('alternate' if index % 2 else ''), tag))


def main():
    root = tk.Tk()
    BackupGuardianApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
