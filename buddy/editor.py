"""C highlighting, line numbers, and indentation without code completion."""
import re
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit

class CHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.formats = {}
        for name, color in {"keyword": "#c5a1ff", "number": "#ffc978", "string": "#72e5ca", "comment": "#8498af", "preprocessor": "#83baff", "function": "#e8d590", "variable": "#9cdcfe"}.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.formats[name] = fmt
        keywords = r"\b(?:auto|break|case|char|const|continue|default|do|double|else|enum|extern|float|for|goto|if|int|long|register|return|short|signed|sizeof|static|struct|switch|typedef|union|unsigned|void|volatile|while|_Bool|_Atomic|_Alignof|_Alignas|_Generic|_Static_assert|_Thread_local|restrict|inline)\b"
        self.tokens = re.compile(r'(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|(?P<comment>//.*|/\*.*?\*/)|(?P<preprocessor>^\s*#.*)|(?P<keyword>' + keywords + r')|(?P<function>\b[A-Za-z_]\w*(?=\s*\())|(?P<variable>\b[A-Za-z_]\w*\b)|(?P<number>\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?)\b)')

    def highlightBlock(self, text):
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() == 1:
            end = text.find("*/")
            if end < 0:
                self.setFormat(0, len(text), self.formats["comment"])
                self.setCurrentBlockState(1)
                return
            start = end + 2
            self.setFormat(0, start, self.formats["comment"])
        # Walk strings/comments first so comment markers inside strings stay harmless.
        cursor = start
        while cursor < len(text):
            match = re.search(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//|/\*', text[cursor:])
            if not match:
                self._tokens(text, cursor, len(text))
                break
            begin = cursor + match.start()
            self._tokens(text, cursor, begin)
            token = match.group()
            if token == "//":
                self.setFormat(begin, len(text) - begin, self.formats["comment"])
                break
            if token == "/*":
                end = text.find("*/", begin + 2)
                if end < 0:
                    self.setFormat(begin, len(text) - begin, self.formats["comment"])
                    self.setCurrentBlockState(1)
                    break
                cursor = end + 2
                self.setFormat(begin, cursor - begin, self.formats["comment"])
            else:
                self.setFormat(begin, len(token), self.formats["string"])
                cursor = begin + len(token)

    def _tokens(self, text, start, end):
        for match in self.tokens.finditer(text, start, end):
            self.setFormat(match.start(), match.end() - match.start(), self.formats[match.lastgroup])

class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_numbers(event)

class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setAccessibleName("Your C code")
        self.setPlaceholderText("Your own solution starts here...")
        self.highlighter = CHighlighter(self.document())
        self.gutter = LineNumbers(self)
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_gutter)
        self.update_margin()
        from PySide6.QtCore import QTimer
        self.diagnostic_timer = QTimer(self)
        self.diagnostic_timer.setSingleShot(True)
        self.diagnostic_timer.setInterval(900)
        self.diagnostic_timer.timeout.connect(self.check_delimiters)
        self.textChanged.connect(lambda: self.diagnostic_timer.start())

    def check_delimiters(self):
        from .analysis import stripped_code
        # Keep offsets stable while ignoring strings and comments.
        text = self.toPlainText()
        pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
        clean = re.sub(pattern, lambda m: " " * len(m.group()), text)
        stack, errors = [], []
        for position, char in enumerate(clean):
            if char in "({[":
                stack.append((char, position))
            elif char in ")}]":
                if not stack or stack[-1][0] != {")": "(", "}": "{", "]": "["}[char]:
                    errors.append(position)
                else:
                    stack.pop()
        # Open blocks are normal while typing; underline only mismatched closers.
        selections = []
        for position in errors:
            selection = QTextEdit.ExtraSelection()
            cursor = QTextCursor(self.document())
            cursor.setPosition(position)
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            selection.format.setUnderlineColor(QColor("#ff7b86"))
            selection.format.setToolTip("This closing bracket does not match the current opening bracket.")
            selections.append(selection)
        self.setExtraSelections(selections)
        self.setToolTip(f"{len(errors)} mismatched closing bracket(s). Local checks cover delimiters only.")

    def gutter_width(self):
        return 16 + self.fontMetrics().horizontalAdvance("9") * len(str(max(1, self.blockCount())))

    def update_margin(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        bounds = self.contentsRect()
        self.gutter.setGeometry(QRect(bounds.left(), bounds.top(), self.gutter_width(), bounds.height()))

    def paint_numbers(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor("#101b2b"))
        painter.setPen(QColor("#8498af"))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible():
                painter.drawText(0, top, self.gutter.width() - 6, height,
                                 Qt.AlignmentFlag.AlignRight, str(block.blockNumber() + 1))
            top += round(self.blockBoundingRect(block).height())
            block = block.next()

    def keyPressEvent(self, event):
        cursor = self.textCursor()
        if not self.isReadOnly() and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            before = cursor.block().text()[:cursor.positionInBlock()]
            indent = re.match(r"[ \t]*", before).group()
            if before.rstrip().endswith("{"):
                indent += "    "
            cursor.beginEditBlock()
            cursor.insertText("\n" + indent)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return
        if not self.isReadOnly() and event.key() == Qt.Key.Key_Tab and not cursor.hasSelection():
            cursor.insertText("    ")
            return
        super().keyPressEvent(event)
