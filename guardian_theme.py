"""Paleta, controles ttk e ilustração local do painel."""

import tkinter as tk
from tkinter import font, ttk

BG = '#edf2f9'
PAPER = '#ffffff'
INK = '#172540'
MUTED = '#516580'
LINE = '#d6e1ef'
BLUE = '#2855d2'
NAV = '#101b35'
NAV_TEXT = '#b9c8df'
GOOD = '#19664b'
BAD = '#a12c3e'


def configure(root):
    installed = set(font.families(root))
    family = 'Segoe UI' if 'Segoe UI' in installed else font.nametofont('TkDefaultFont').actual('family')
    fonts = {
        'small': (family, 9),
        'body': (family, 10),
        'bold': (family, 10, 'bold'),
        'section': (family, 13, 'bold'),
        'metric': (family, 22, 'bold'),
        'title': (family, 27, 'bold'),
    }
    gui = ttk.Style(root)
    gui.theme_use('clam')
    for name, background, foreground, border, hover, focused, padding in (
        ('Primary', BLUE, PAPER, BLUE, '#1f46b7', '#82a7ff', (17, 9)),
        ('Secondary', '#edf3ff', '#234477', '#d5e3ff', '#dce9ff', BLUE, (14, 8)),
        ('Nav', NAV, NAV_TEXT, NAV, '#1b2e53', '#77a2ff', (14, 10)),
        ('Current', '#223a68', PAPER, '#365887', '#294777', '#9ebcff', (14, 10)),
    ):
        style = f'{name}.TButton'
        gui.configure(style, background=background, foreground=foreground, bordercolor=border,
                      lightcolor=border, darkcolor=border, relief='flat', focusthickness=2,
                      focuscolor=focused, padding=padding, font=fonts['bold'],
                      anchor='w' if name in ('Nav', 'Current') else 'center')
        gui.map(style, background=[('disabled', background), ('pressed', hover), ('active', hover)],
                foreground=[('disabled', '#adbed7' if name in ('Nav', 'Current') else '#808c9d')],
                bordercolor=[('focus', focused)])
    gui.configure('Guardian.TEntry', font=fonts['body'], fieldbackground=PAPER, foreground=INK,
                  bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=8)
    gui.map('Guardian.TEntry', bordercolor=[('focus', BLUE)], fieldbackground=[('disabled', BG)])
    gui.configure('Guardian.Treeview', background=PAPER, fieldbackground=PAPER, foreground=INK,
                  rowheight=29, borderwidth=0, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                  font=fonts['body'])
    gui.map('Guardian.Treeview', background=[('selected', '#ddeaff')], foreground=[('selected', '#173c80')])
    gui.configure('Guardian.Treeview.Heading', background='#eef3fb', foreground=MUTED,
                  relief='flat', padding=(8, 7), font=fonts['bold'])
    gui.map('Guardian.Treeview.Heading', background=[('active', '#eef3fb')])
    gui.layout('Guardian.Vertical.TScrollbar', [
        ('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
            ('Vertical.Scrollbar.thumb', {'sticky': 'nswe', 'expand': '1'}),
        ]}),
    ])
    gui.configure('Guardian.Vertical.TScrollbar', background='#9db2d3', troughcolor='#eef3f9',
                  bordercolor='#eef3f9', lightcolor='#9db2d3', darkcolor='#9db2d3',
                  relief='flat', gripcount=0, arrowsize=12)
    gui.map('Guardian.Vertical.TScrollbar', background=[('active', '#7898c4')])
    gui.configure('Guardian.Horizontal.TProgressbar', background=BLUE, troughcolor='#dce7fc',
                  bordercolor='#dce7fc', lightcolor=BLUE, darkcolor=BLUE, thickness=5)
    return fonts


class VaultBanner(tk.Canvas):
    def __init__(self, parent, fonts, button, title, location):
        super().__init__(parent, height=132, bg='#182d63', highlightthickness=0)
        self.fonts = fonts
        self.title = title
        self.location = location
        self.control = self.create_window(22, 103, anchor='w', window=button(self))
        self.bind('<Configure>', self.draw)

    def draw(self, event):
        self.delete('art')
        width = event.width
        for band in range(36):
            a, b = width * band // 36, width * (band + 1) // 36 + 1
            color = f'#{24 + band // 2:02x}{45 + band:02x}{99 + band * 2:02x}'
            self.create_rectangle(a, 0, b, 132, fill=color, outline='', tags='art')
        for x in range(max(width - 274, 380), width, 19):
            for y in range(10, 131, 19):
                self.create_oval(x, y, x + 2, y + 2, fill='#6787d2', outline='', tags='art')
        x = width - 118
        if width >= 550:
            self.create_oval(x - 81, -8, x + 81, 154, outline='#5d7dd1', width=2, tags='art')
            for y in (35, 62, 89):
                self.create_polygon(x - 54, y, x - 38, y - 10, x + 38, y - 10, x + 54, y,
                                    x + 54, y + 14, x - 54, y + 14, fill='#233a83',
                                    outline='#a4bfff', width=2, tags='art')
                self.create_line(x - 54, y, x + 54, y, fill='#769eff', tags='art')
                self.create_line(x - 44, y + 7, x - 13, y + 7, fill='#779be6', width=2, tags='art')
                for dx in (30, 39):
                    self.create_oval(x + dx, y + 4, x + dx + 5, y + 9,
                                     fill='#80ead5', outline='', tags='art')
        self.create_text(22, 18, text='PASTA DE BACKUPS', anchor='nw', fill='#bad0ff',
                         font=self.fonts['small'], tags='art')
        self.create_text(22, 63 if self.location else 41, text=self.location or self.title,
                         anchor='nw', fill='#d9e6ff' if self.location else PAPER,
                         font=self.fonts['small' if self.location else 'section'], tags='art')
        if self.location:
            self.create_text(22, 37, text=self.title, anchor='nw', fill=PAPER,
                             font=self.fonts['section'], tags='art')
        self.tag_raise(self.control)
