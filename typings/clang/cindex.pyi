# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
# Types for the part of libclang's Python bindings pybrokkr.fallbacks reads; the bindings declare none.

from collections.abc import Iterator

class CursorKind:
    BREAK_STMT: CursorKind
    CLASS_DECL: CursorKind
    CLASS_TEMPLATE: CursorKind
    CLASS_TEMPLATE_PARTIAL_SPECIALIZATION: CursorKind
    COMPOUND_STMT: CursorKind
    CONSTRUCTOR: CursorKind
    CONTINUE_STMT: CursorKind
    CONVERSION_FUNCTION: CursorKind
    CXX_CATCH_STMT: CursorKind
    CXX_METHOD: CursorKind
    DESTRUCTOR: CursorKind
    FUNCTION_DECL: CursorKind
    FUNCTION_TEMPLATE: CursorKind
    IF_STMT: CursorKind
    MEMBER_REF_EXPR: CursorKind
    RETURN_STMT: CursorKind
    STRUCT_DECL: CursorKind

class File:
    @property
    def name(self) -> str: ...

class SourceLocation:
    @property
    def file(self) -> File | None: ...
    @property
    def line(self) -> int: ...
    @property
    def offset(self) -> int: ...

class SourceRange:
    @property
    def start(self) -> SourceLocation: ...
    @property
    def end(self) -> SourceLocation: ...

class Token:
    @property
    def spelling(self) -> str: ...
    @property
    def extent(self) -> SourceRange: ...

class Cursor:
    @property
    def kind(self) -> CursorKind: ...
    @property
    def spelling(self) -> str: ...
    @property
    def semantic_parent(self) -> Cursor | None: ...
    @property
    def location(self) -> SourceLocation: ...
    @property
    def extent(self) -> SourceRange: ...
    def get_children(self) -> Iterator[Cursor]: ...
    def get_tokens(self) -> Iterator[Token]: ...
    def is_definition(self) -> bool: ...

class Diagnostic:
    Error: int
    @property
    def severity(self) -> int: ...

class TranslationUnit:
    @property
    def cursor(self) -> Cursor: ...
    @property
    def diagnostics(self) -> Iterator[Diagnostic]: ...

class TranslationUnitLoadError(Exception): ...

class Index:
    @staticmethod
    def create() -> Index: ...
    def parse(self, path: str, args: list[str] | None = None) -> TranslationUnit: ...
