from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tools import gui
from tools.preview import PreviewResult
from tools.preview import PreviewResult as PreviewStub


class FakeWidget:
    def __init__(self, master=None, **kwargs):
        self.master = master
        self.kwargs = dict(kwargs)
        self.grid_calls = []
        self.columnconfigure_calls = []
        self.rowconfigure_calls = []
        self.bindings = {}

    def grid(self, *args, **kwargs):
        self.grid_calls.append((args, kwargs))

    def columnconfigure(self, index, weight=0):
        self.columnconfigure_calls.append((index, weight))

    def rowconfigure(self, index, weight=0):
        self.rowconfigure_calls.append((index, weight))

    def cget(self, key):
        return self.kwargs.get(key)

    def bind(self, event, handler):
        self.bindings[event] = handler

    def event_generate(self, event):
        handler = self.bindings.get(event)
        if handler is not None:
            handler(None)

    def configure(self, **kwargs):
        self.kwargs.update(kwargs)

    config = configure


class FakeRoot(FakeWidget):
    def __init__(self):
        super().__init__(None)
        self.title_value = None
        self.geometry_value = None
        self.after_calls = []

    def title(self, text):
        self.title_value = text

    def geometry(self, value):
        self.geometry_value = value

    def after(self, delay_ms, callback=None, *args):
        self.after_calls.append((delay_ms, callback, args))
        if callback is not None:
            return callback(*args)

    def update_idletasks(self):
        return None


class FakeTkModule:
    DISABLED = "disabled"
    NORMAL = "normal"
    END = "end"

    class Listbox(FakeWidget):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            self.items = []
            self.selected_indices = ()

        def insert(self, index, value):
            self.items.append(value)

        def delete(self, start, end=None):
            self.items.clear()
            self.selected_indices = ()

        def curselection(self):
            return self.selected_indices

        def get(self, index):
            return self.items[index]

        def selection_set(self, index):
            self.selected_indices = (index,)

        def selection_clear(self):
            self.selected_indices = ()

    class Text(FakeWidget):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            self.content = ""

        def configure(self, **kwargs):
            self.kwargs.update(kwargs)

        config = configure

        def delete(self, start, end=None):
            self.content = ""

        def insert(self, index, text):
            self.content = text

    @staticmethod
    def Tk():
        return FakeRoot()


class FakeTtkModule:
    class Style:
        def __init__(self):
            self.theme = None
            self.configured = {}
            self.mapped = {}

        def theme_use(self, name):
            self.theme = name

        def configure(self, style_name, **kwargs):
            self.configured[style_name] = kwargs

        def map(self, style_name, **kwargs):
            self.mapped[style_name] = kwargs

    class Frame(FakeWidget):
        pass

    class Label(FakeWidget):
        pass

    class Entry(FakeWidget):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            self.value = ""

        def get(self):
            return self.value

        def set_value(self, value):
            self.value = value

    class Button(FakeWidget):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            self.command = kwargs.get("command")

        def invoke(self):
            if self.command is not None:
                self.command()


@dataclass
class ServiceSentinel:
    called: bool = False

    def __getattr__(self, name):
        raise AssertionError(f"Service method should not be called during construction: {name}")


def _patch_tk(monkeypatch) -> None:
    monkeypatch.setattr(gui, "tk", FakeTkModule)
    monkeypatch.setattr(gui, "ttk", FakeTtkModule)


class ImmediateThread:
    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon

    def start(self):
        self.target(*self.args, **self.kwargs)


def _patch_threading(monkeypatch) -> None:
    monkeypatch.setattr(gui.threading, "Thread", ImmediateThread)


def _write_valid_defs_root(root: Path, def_name: str = "Thing") -> None:
    defs_dir = root / "Defs"
    defs_dir.mkdir(parents=True, exist_ok=True)
    (defs_dir / "ThingDefs.xml").write_text(
        f"""
        <Defs>
            <ThingDef>
                <defName>{def_name}</defName>
            </ThingDef>
        </Defs>
        """,
        encoding="utf-8",
    )


def test_window_constructs_successfully(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    app = gui.SteamExpansionApp(service=ServiceSentinel())

    assert app.root is not None
    assert app.root.title_value == "Steam Expansion"
    assert app.root.geometry_value == "1200x760"


def test_all_major_widgets_exist(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    app = gui.SteamExpansionApp(service=ServiceSentinel())

    assert app.left_panel is not None
    assert app.right_panel is not None
    assert app.bottom_panel is not None

    assert app.search_label is not None
    assert app.search_entry is not None
    assert app.search_button is not None
    assert app.search_results_listbox is not None

    assert app.inspection_report_text is not None
    assert app.preview_text is not None
    assert app.generate_patch_button is not None


def test_generate_button_starts_disabled(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    app = gui.SteamExpansionApp(service=ServiceSentinel())

    assert app.generate_patch_button.cget("state") == FakeTkModule.DISABLED


def test_dependency_injection_works(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FailIfConstructed:
        def __init__(self):
            raise AssertionError("Default service should not be constructed when injected")

    monkeypatch.setattr(gui, "SteamExpansionService", FailIfConstructed)

    injected = ServiceSentinel()
    app = gui.SteamExpansionApp(service=injected)

    assert app.service is injected


def test_no_backend_logic_executed_during_construction(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    counts = {"init": 0}

    class FakeService:
        def __init__(self):
            counts["init"] += 1

        def search(self, *args, **kwargs):
            raise AssertionError("search should not be called during construction")

        def inspect(self, *args, **kwargs):
            raise AssertionError("inspect should not be called during construction")

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called during construction")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called during construction")

    monkeypatch.setattr(gui, "SteamExpansionService", FakeService)

    app = gui.SteamExpansionApp()

    assert app.service is not None
    assert counts["init"] == 1


def test_search_button_calls_service(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.calls = []

        def search(self, term, defs_dir):
            self.calls.append((term, defs_dir))
            return ["Alpha", "Beta"]

        def inspect(self, *args, **kwargs):
            raise AssertionError("inspect should not be called")

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service, defs_dir="CustomDefs")
    app.search_entry.set_value("mech")

    app.search_button.invoke()

    assert service.calls == [("mech", "CustomDefs")]


def test_enter_key_calls_same_search_handler(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.calls = []

        def search(self, term, defs_dir):
            self.calls.append((term, defs_dir))
            return ["Result"]

        def inspect(self, *args, **kwargs):
            raise AssertionError("inspect should not be called")

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service, defs_dir="DefsPath")
    app.search_entry.set_value("gestator")

    app.search_entry.event_generate("<Return>")

    assert service.calls == [("gestator", "DefsPath")]


def test_results_populate_listbox(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def search(self, term, defs_dir):
            return ["Alpha", "Beta", "Gamma"]

        def inspect(self, *args, **kwargs):
            raise AssertionError("inspect should not be called")

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("a")

    app.search_button.invoke()

    assert app.search_results_listbox.items == ["Alpha", "Beta", "Gamma"]


def test_existing_results_cleared_before_new_search(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.calls = 0

        def search(self, term, defs_dir):
            self.calls += 1
            if self.calls == 1:
                return ["One", "Two"]
            return ["Three"]

        def inspect(self, *args, **kwargs):
            raise AssertionError("inspect should not be called")

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("first")
    app.search_button.invoke()
    assert app.search_results_listbox.items == ["One", "Two"]

    app.search_entry.set_value("second")
    app.search_button.invoke()

    assert app.search_results_listbox.items == ["Three"]


def test_empty_search_results_leave_listbox_empty(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def search(self, term, defs_dir):
            return []

        def inspect(self, *args, **kwargs):
            raise AssertionError("inspect should not be called")

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_results_listbox.items = ["Old"]
    app.search_entry.set_value("none")

    app.search_button.invoke()

    assert app.search_results_listbox.items == []


def test_no_backend_methods_other_than_search_are_called(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.search_calls = 0

        def search(self, term, defs_dir):
            self.search_calls += 1
            return ["OnlySearch"]

        def inspect(self, *args, **kwargs):
            raise AssertionError("inspect should not be called")

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service)
    app.search_entry.set_value("x")

    app.search_button.invoke()

    assert service.search_calls == 1


def test_selecting_item_calls_inspect(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.inspect_calls = []

        def search(self, term, defs_dir):
            return ["ThingA"]

        def inspect(self, def_name, defs_dir):
            self.inspect_calls.append((def_name, defs_dir))
            return "REPORT A"

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service, defs_dir="DefsPath")
    app.search_entry.set_value("thing")
    app.search_button.invoke()
    app.search_results_listbox.selection_set(0)

    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert service.inspect_calls == [("ThingA", "DefsPath")]


def test_inspection_report_appears_in_widget(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def search(self, term, defs_dir):
            return ["ThingB"]

        def inspect(self, def_name, defs_dir):
            return "Inspection Report"

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("thing")
    app.search_button.invoke()
    app.search_results_listbox.selection_set(0)

    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert app.inspection_report_text.content == "Inspection Report"
    assert app.inspection_report_text.cget("state") == FakeTkModule.DISABLED


def test_previous_report_is_cleared(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.inspect_count = 0

        def search(self, term, defs_dir):
            return ["One", "Two"]

        def inspect(self, def_name, defs_dir):
            self.inspect_count += 1
            if self.inspect_count == 1:
                return "Old Report"
            return "New Report"

        def preview(self, *args, **kwargs):
            return None

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("x")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    assert app.inspection_report_text.content == "Old Report"

    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    assert app.inspection_report_text.content == "New Report"


def test_empty_selection_leaves_panel_empty(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def search(self, term, defs_dir):
            return ["ThingA"]

        def inspect(self, def_name, defs_dir):
            raise AssertionError("inspect should not be called with empty selection")

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.inspection_report_text.content = "Previous"
    app.search_entry.set_value("thing")
    app.search_button.invoke()
    app.search_results_listbox.selection_clear()

    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert app.inspection_report_text.content == ""
    assert app.inspection_report_text.cget("state") == FakeTkModule.DISABLED


def test_search_continues_to_work_with_inspection_enabled(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.search_calls = 0

        def search(self, term, defs_dir):
            self.search_calls += 1
            return ["Alpha", "Beta"]

        def inspect(self, def_name, defs_dir):
            return "Report"

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service)
    app.search_entry.set_value("mech")

    app.search_button.invoke()

    assert service.search_calls == 1
    assert app.search_results_listbox.items == ["Alpha", "Beta"]


def test_no_preview_or_generation_methods_called(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def search(self, term, defs_dir):
            return ["ThingA"]

        def inspect(self, def_name, defs_dir):
            return "Report"

        def preview(self, *args, **kwargs):
            raise AssertionError("preview should not be called")

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("thing")
    app.search_button.invoke()
    app.search_results_listbox.selection_set(0)

    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert app.generate_patch_button.cget("state") == FakeTkModule.DISABLED


def test_preview_service_is_called(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.preview_calls = []

        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            self.preview_calls.append((source, target, defs_dir, tuple(profile), texture_path))
            return PreviewResult(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData",),
                texture_override=texture_path,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service, defs_dir="DefsPath")
    app.search_entry.set_value("thing")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert len(service.preview_calls) == 1
    call = service.preview_calls[0]
    assert call[0] == "SourceThing"
    assert call[1] == "TargetThing"
    assert call[2] == "DefsPath"
    assert call[4] is None


def test_preview_appears_in_preview_widget(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            return PreviewResult(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData", "uiIconPath"),
                texture_override=None,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("thing")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    preview_text = app.preview_text.content
    assert "Source: SourceThing" in preview_text
    assert "Target: TargetThing" in preview_text
    assert "Fields that will change: graphicData, uiIconPath" in preview_text
    assert "Texture override: (none)" in preview_text
    assert "Validation-ready: True" in preview_text
    assert "Profile used:" in preview_text


def test_browse_selection_stores_local_texture_path(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)

    selected_png = tmp_path / "custom.png"
    selected_png.write_bytes(b"fake-png")
    resolved_calls = []

    class FakeFileDialog:
        @staticmethod
        def askopenfilename(**kwargs):
            return str(selected_png)

    class FakeService:
        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, *args, **kwargs):
            return None

        def generate(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)

    def fake_resolve_texture_path(texture, texture_file):
        resolved_calls.append((texture, texture_file))
        return "Textures/ConvertedTexture"

    monkeypatch.setattr(gui, "resolve_texture_path", fake_resolve_texture_path)

    app = gui.SteamExpansionApp(service=FakeService())
    app.browse_texture_button.invoke()

    assert app.selected_texture_path == str(selected_png)
    assert app.texture_override_path == "Textures/ConvertedTexture"
    assert app.texture_override_entry.get() == str(selected_png)
    assert resolved_calls == [(None, str(selected_png))]


def test_texture_selection_refreshes_preview(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)

    selected_png = tmp_path / "refresh.png"
    selected_png.write_bytes(b"png")

    class FakeFileDialog:
        @staticmethod
        def askopenfilename(**kwargs):
            return str(selected_png)

    class FakeService:
        def __init__(self):
            self.preview_calls = []

        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            self.preview_calls.append((source, target, defs_dir, tuple(profile), texture_path))
            return PreviewResult(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData",),
                texture_override=texture_path,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "resolve_texture_path", lambda texture, texture_file: "Textures/Refresh")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service)
    app.search_entry.set_value("thing")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert service.preview_calls[-1][4] is None

    app.browse_texture_button.invoke()

    assert app.preview_text.content.count("Texture override: Textures/Refresh") == 1
    assert service.preview_calls[-1][4] == "Textures/Refresh"


def test_clearing_texture_removes_override_and_generation_uses_none(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)

    selected_png = tmp_path / "clear.png"
    selected_png.write_bytes(b"png")

    class FakeFileDialog:
        @staticmethod
        def askopenfilename(**kwargs):
            return str(selected_png)

    class FakeService:
        def __init__(self):
            self.generate_calls = []
            self.preview_calls = []

        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            self.preview_calls.append(texture_path)
            return PreviewResult(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData",),
                texture_override=texture_path,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, source, target, defs_dir, profile, texture_path=None):
            self.generate_calls.append(texture_path)
            return ""

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "resolve_texture_path", lambda texture, texture_file: "Textures/Cleared")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service)
    app.search_entry.set_value("thing")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    app.browse_texture_button.invoke()
    assert app.preview_text.content.count("Texture override: Textures/Cleared") == 1
    assert app.current_preview.texture_override == "Textures/Cleared"

    app.clear_texture_button.invoke()

    assert app.selected_texture_path is None
    assert app.texture_override_path is None
    assert app.texture_override_entry.get() == ""
    assert app.preview_text.content.count("Texture override: (none)") == 1
    assert service.preview_calls[-1] is None
    assert service.generate_calls == []


def test_generation_uses_selected_texture_override(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)

    selected_png = tmp_path / "generate.png"
    selected_png.write_bytes(b"png")

    class FakeFileDialog:
        @staticmethod
        def askopenfilename(**kwargs):
            return str(selected_png)

        @staticmethod
        def asksaveasfilename(**kwargs):
            return str(tmp_path / "generated.xml")

    class FakeService:
        def __init__(self):
            self.generate_calls = []

        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, *args, **kwargs):
            return PreviewResult(
                source_defName="SourceThing",
                target_defName="TargetThing",
                changed_fields=("graphicData",),
                texture_override=None,
                validation_ready=True,
                profile=("graphicData",),
            )

        def generate(self, source, target, defs_dir, profile, texture_path=None):
            self.generate_calls.append(texture_path)
            return ""

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "resolve_texture_path", lambda texture, texture_file: "Textures/Generated")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service)
    app.search_entry.set_value("thing")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    app.browse_texture_button.invoke()
    app.generate_patch_button.invoke()

    assert service.generate_calls == ["Textures/Generated"]


def test_no_files_written_when_selecting_or_clearing_texture(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)

    selected_png = tmp_path / "selection.png"
    selected_png.write_bytes(b"png")

    class FakeFileDialog:
        @staticmethod
        def askopenfilename(**kwargs):
            return str(selected_png)

    class FakeService:
        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, *args, **kwargs):
            return None

        def generate(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "resolve_texture_path", lambda texture, texture_file: "Textures/NoWrite")

    app = gui.SteamExpansionApp(service=FakeService())
    app.browse_texture_button.invoke()
    app.clear_texture_button.invoke()

    assert not (tmp_path / "written-output.xml").exists()


def test_previous_preview_is_cleared(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.preview_count = 0

        def search(self, term, defs_dir):
            return ["A", "B", "C"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            self.preview_count += 1
            if self.preview_count == 1:
                return PreviewResult(
                    source_defName=source,
                    target_defName=target,
                    changed_fields=("graphicData",),
                    texture_override=None,
                    validation_ready=True,
                    profile=tuple(profile),
                )
            return PreviewResult(
                source_defName=source,
                target_defName=target,
                changed_fields=("uiIconPath",),
                texture_override=None,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("x")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    assert "Fields that will change: graphicData" in app.preview_text.content

    app.search_results_listbox.selection_set(2)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    assert "Fields that will change: uiIconPath" in app.preview_text.content


def test_empty_preview_leaves_widget_empty(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            return None

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.preview_text.content = "Old Preview"
    app.search_entry.set_value("thing")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert app.preview_text.content == ""


def test_search_and_inspection_continue_to_work_with_preview(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.search_calls = 0
            self.inspect_calls = 0

        def search(self, term, defs_dir):
            self.search_calls += 1
            return ["One", "Two"]

        def inspect(self, def_name, defs_dir):
            self.inspect_calls += 1
            return "Inspection Body"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            return None

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    service = FakeService()
    app = gui.SteamExpansionApp(service=service)
    app.search_entry.set_value("term")
    app.search_button.invoke()
    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert service.search_calls == 1
    assert service.inspect_calls == 1
    assert app.search_results_listbox.items == ["One", "Two"]
    assert app.inspection_report_text.content == "Inspection Body"


def test_no_generate_methods_are_called_with_preview(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def __init__(self):
            self.generate_calls = 0

        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            return PreviewResult(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData",),
                texture_override=None,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, *args, **kwargs):
            self.generate_calls += 1
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("thing")
    app.search_button.invoke()
    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert app.generate_patch_button.cget("state") == FakeTkModule.NORMAL
    assert app.service.generate_calls == 0


def test_configuration_persistence(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)
    _patch_threading(monkeypatch)

    config_path = tmp_path / "gui-config.json"
    defs_root = tmp_path / "selected-defs"
    _write_valid_defs_root(defs_root, "PersistedThing")

    class FakeFileDialog:
        @staticmethod
        def askdirectory(**kwargs):
            return str(defs_root)

    class FakeMessageBox:
        @staticmethod
        def showerror(title, message):
            raise AssertionError("showerror should not be called")

        @staticmethod
        def showinfo(title, message):
            raise AssertionError("showinfo should not be called")

    class FakeService:
        def reload_cache(self, defs_dir):
            return None

        def search(self, term, defs_dir):
            return []

        def inspect(self, def_name, defs_dir):
            return ""

        def preview(self, *args, **kwargs):
            return None

        def generate(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "messagebox", FakeMessageBox)

    app = gui.SteamExpansionApp(service=FakeService(), config_path=config_path)
    app.browse_defs_button.invoke()

    assert config_path.exists()
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"defs_dir": str(defs_root)}

    reopened = gui.SteamExpansionApp(service=FakeService(), config_path=config_path)

    assert reopened.defs_dir == str(defs_root)
    assert reopened.defs_dir_label.cget("text") == str(defs_root)


def test_invalid_directory_handling(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)

    invalid_dir = tmp_path / "missing-defs"
    errors = []

    class FakeFileDialog:
        @staticmethod
        def askdirectory(**kwargs):
            return str(invalid_dir)

    class FakeMessageBox:
        @staticmethod
        def showerror(title, message):
            errors.append((title, message))

        @staticmethod
        def showinfo(title, message):
            raise AssertionError("showinfo should not be called")

    class FakeService:
        def reload_cache(self, defs_dir):
            raise AssertionError("reload_cache should not be called for invalid folders")

        def search(self, term, defs_dir):
            return []

        def inspect(self, def_name, defs_dir):
            return ""

        def preview(self, *args, **kwargs):
            return None

        def generate(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "messagebox", FakeMessageBox)

    app = gui.SteamExpansionApp(service=FakeService(), config_path=tmp_path / "config.json")
    original_defs_dir = app.defs_dir

    app.browse_defs_button.invoke()

    assert errors
    assert "does not exist" in errors[0][1]
    assert app.defs_dir == original_defs_dir


def test_successful_directory_switching(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)
    _patch_threading(monkeypatch)

    first_defs_root = tmp_path / "first"
    second_defs_root = tmp_path / "second"
    _write_valid_defs_root(first_defs_root, "FirstThing")
    _write_valid_defs_root(second_defs_root, "SecondThing")

    class FakeFileDialog:
        @staticmethod
        def askdirectory(**kwargs):
            return str(second_defs_root)

    class FakeMessageBox:
        @staticmethod
        def showerror(title, message):
            raise AssertionError("showerror should not be called")

        @staticmethod
        def showinfo(title, message):
            raise AssertionError("showinfo should not be called")

    class FakeService:
        def __init__(self):
            self.reload_calls = []
            self.search_calls = []

        def reload_cache(self, defs_dir):
            self.reload_calls.append(str(defs_dir))

        def search(self, term, defs_dir):
            self.search_calls.append((term, str(defs_dir)))
            if str(defs_dir) == str(second_defs_root):
                return ["SecondThing"]
            return ["FirstThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, *args, **kwargs):
            return PreviewStub(
                source_defName="Source",
                target_defName="Target",
                changed_fields=("graphicData",),
                texture_override=None,
                validation_ready=True,
                profile=("graphicData",),
            )

        def generate(self, *args, **kwargs):
            return "<Patch/>"

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "messagebox", FakeMessageBox)

    app = gui.SteamExpansionApp(service=FakeService(), defs_dir=str(first_defs_root), config_path=tmp_path / "config.json")
    app.browse_defs_button.invoke()

    assert app.defs_dir == str(second_defs_root)
    assert app.defs_dir_label.cget("text") == str(second_defs_root)
    assert app.service.reload_calls == [str(second_defs_root)]

    app.search_entry.set_value("thing")
    app.search_button.invoke()

    assert app.search_results_listbox.items == ["SecondThing"]
    assert app.service.search_calls[-1] == ("thing", str(second_defs_root))


def test_cache_reload_after_folder_change(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)
    _patch_threading(monkeypatch)

    first_defs_root = tmp_path / "first"
    second_defs_root = tmp_path / "second"
    _write_valid_defs_root(first_defs_root, "FirstThing")
    _write_valid_defs_root(second_defs_root, "SecondThing")

    class FakeFileDialog:
        @staticmethod
        def askdirectory(**kwargs):
            return str(second_defs_root)

    class FakeMessageBox:
        @staticmethod
        def showerror(title, message):
            raise AssertionError("showerror should not be called")

        @staticmethod
        def showinfo(title, message):
            raise AssertionError("showinfo should not be called")

    class FakeService:
        def __init__(self):
            self.loaded_defs_dir = str(first_defs_root)
            self.reload_calls = []

        def reload_cache(self, defs_dir):
            self.loaded_defs_dir = str(defs_dir)
            self.reload_calls.append(str(defs_dir))

        def search(self, term, defs_dir):
            if self.loaded_defs_dir == str(second_defs_root):
                return ["SecondThing"]
            return ["FirstThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, *args, **kwargs):
            return PreviewStub(
                source_defName="Source",
                target_defName="Target",
                changed_fields=("graphicData",),
                texture_override=None,
                validation_ready=True,
                profile=("graphicData",),
            )

        def generate(self, *args, **kwargs):
            return "<Patch/>"

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "messagebox", FakeMessageBox)

    service = FakeService()
    app = gui.SteamExpansionApp(service=service, defs_dir=str(first_defs_root), config_path=tmp_path / "config.json")

    app.search_entry.set_value("thing")
    app.search_button.invoke()
    assert app.search_results_listbox.items == ["FirstThing"]

    app.browse_defs_button.invoke()

    app.search_entry.set_value("thing")
    app.search_button.invoke()

    assert service.reload_calls == [str(second_defs_root)]
    assert app.search_results_listbox.items == ["SecondThing"]


def test_generate_button_enabled_after_valid_preview(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    class FakeService:
        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            return PreviewStub(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData",),
                texture_override=None,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, *args, **kwargs):
            raise AssertionError("generate should not be called")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("thing")
    app.search_button.invoke()

    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    assert app.generate_patch_button.cget("state") == FakeTkModule.DISABLED

    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    assert app.generate_patch_button.cget("state") == FakeTkModule.NORMAL


def test_successful_save_writes_xml_and_shows_success_message(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)

    save_path = tmp_path / "patch.xml"
    save_calls = {"count": 0}
    message_calls = []

    class FakeFileDialog:
        @staticmethod
        def asksaveasfilename(**kwargs):
            save_calls["count"] += 1
            return str(save_path)

    class FakeMessageBox:
        @staticmethod
        def showinfo(title, message):
            message_calls.append((title, message))

        @staticmethod
        def showerror(title, message):
            raise AssertionError("showerror should not be called on success")

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "messagebox", FakeMessageBox)

    class FakeService:
        def __init__(self):
            self.generate_calls = []

        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            return PreviewStub(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData",),
                texture_override=None,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, source, target, defs_dir, profile, texture_path=None):
            self.generate_calls.append((source, target, defs_dir, tuple(profile), texture_path))
            return "<Patch>Generated</Patch>"

    service = FakeService()
    app = gui.SteamExpansionApp(service=service, defs_dir="DefsPath")
    app.search_entry.set_value("thing")
    app.search_button.invoke()
    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    assert app.generate_patch_button.cget("state") == FakeTkModule.NORMAL

    app.generate_patch_button.invoke()

    assert save_calls["count"] == 1
    assert len(service.generate_calls) == 1
    assert save_path.read_text(encoding="utf-8") == "<Patch>Generated</Patch>"
    assert message_calls == [("Patch Saved", f"Patch written to {save_path}")]


def test_cancelled_save_dialog_does_not_generate(monkeypatch) -> None:
    _patch_tk(monkeypatch)

    save_calls = {"count": 0}

    class FakeFileDialog:
        @staticmethod
        def asksaveasfilename(**kwargs):
            save_calls["count"] += 1
            return ""

    class FakeMessageBox:
        @staticmethod
        def showinfo(title, message):
            raise AssertionError("showinfo should not be called when canceled")

        @staticmethod
        def showerror(title, message):
            raise AssertionError("showerror should not be called when canceled")

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "messagebox", FakeMessageBox)

    class FakeService:
        def __init__(self):
            self.generate_calls = 0

        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            return PreviewStub(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData",),
                texture_override=None,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, *args, **kwargs):
            self.generate_calls += 1
            return "<Patch/>"

    service = FakeService()
    app = gui.SteamExpansionApp(service=service)
    app.search_entry.set_value("thing")
    app.search_button.invoke()
    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    app.generate_patch_button.invoke()

    assert save_calls["count"] == 1
    assert service.generate_calls == 0


def test_generation_error_handling(monkeypatch, tmp_path) -> None:
    _patch_tk(monkeypatch)

    save_path = tmp_path / "broken.xml"
    error_messages = []

    class FakeFileDialog:
        @staticmethod
        def asksaveasfilename(**kwargs):
            return str(save_path)

    class FakeMessageBox:
        @staticmethod
        def showinfo(title, message):
            raise AssertionError("showinfo should not be called on failure")

        @staticmethod
        def showerror(title, message):
            error_messages.append((title, message))

    monkeypatch.setattr(gui, "filedialog", FakeFileDialog)
    monkeypatch.setattr(gui, "messagebox", FakeMessageBox)

    class FakeService:
        def search(self, term, defs_dir):
            return ["SourceThing", "TargetThing"]

        def inspect(self, def_name, defs_dir):
            return f"Inspect {def_name}"

        def preview(self, source, target, defs_dir, profile, texture_path=None):
            return PreviewStub(
                source_defName=source,
                target_defName=target,
                changed_fields=("graphicData",),
                texture_override=None,
                validation_ready=True,
                profile=tuple(profile),
            )

        def generate(self, *args, **kwargs):
            raise RuntimeError("backend failed")

    app = gui.SteamExpansionApp(service=FakeService())
    app.search_entry.set_value("thing")
    app.search_button.invoke()
    app.search_results_listbox.selection_set(0)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")
    app.search_results_listbox.selection_set(1)
    app.search_results_listbox.event_generate("<<ListboxSelect>>")

    app.generate_patch_button.invoke()

    assert error_messages == [("Patch Generation Failed", "Unable to generate patch: backend failed")]
    assert not save_path.exists()
