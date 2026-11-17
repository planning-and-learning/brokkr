# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
# Types for the part of libclang's Python bindings pybrokkr.rules reads (coding.fallbacks, template.unity_check,
# schema.records); the bindings declare none.

from collections.abc import Iterator

class CursorKind:
    STRING_LITERAL: CursorKind
    LAMBDA_EXPR: CursorKind
    BREAK_STMT: CursorKind
    CALL_EXPR: CursorKind
    UNARY_OPERATOR: CursorKind
    PARM_DECL: CursorKind
    PAREN_EXPR: CursorKind
    OVERLOADED_DECL_REF: CursorKind
    CXX_THIS_EXPR: CursorKind
    CXX_STATIC_CAST_EXPR: CursorKind
    CXX_FUNCTIONAL_CAST_EXPR: CursorKind
    CSTYLE_CAST_EXPR: CursorKind
    CLASS_DECL: CursorKind
    CLASS_TEMPLATE: CursorKind
    CLASS_TEMPLATE_PARTIAL_SPECIALIZATION: CursorKind
    COMPOUND_STMT: CursorKind
    CONSTRUCTOR: CursorKind
    CONTINUE_STMT: CursorKind
    CONVERSION_FUNCTION: CursorKind
    CXX_ACCESS_SPEC_DECL: CursorKind
    CXX_BASE_SPECIFIER: CursorKind
    CXX_CATCH_STMT: CursorKind
    CXX_METHOD: CursorKind
    DECL_REF_EXPR: CursorKind
    DESTRUCTOR: CursorKind
    FIELD_DECL: CursorKind
    FUNCTION_DECL: CursorKind
    FUNCTION_TEMPLATE: CursorKind
    IF_STMT: CursorKind
    INCLUSION_DIRECTIVE: CursorKind
    MACRO_DEFINITION: CursorKind
    MEMBER_REF_EXPR: CursorKind
    NAMESPACE: CursorKind
    NAMESPACE_REF: CursorKind
    RETURN_STMT: CursorKind
    STRUCT_DECL: CursorKind
    TEMPLATE_NON_TYPE_PARAMETER: CursorKind
    TEMPLATE_REF: CursorKind
    TEMPLATE_TEMPLATE_PARAMETER: CursorKind
    TEMPLATE_TYPE_PARAMETER: CursorKind
    TRANSLATION_UNIT: CursorKind
    TYPE_ALIAS_DECL: CursorKind
    TYPE_ALIAS_TEMPLATE_DECL: CursorKind
    TYPE_REF: CursorKind
    TYPEDEF_DECL: CursorKind
    UNEXPOSED_EXPR: CursorKind
    VAR_DECL: CursorKind
    @property
    def name(self) -> str: ...
    def is_declaration(self) -> bool: ...
    def is_expression(self) -> bool: ...
    def is_attribute(self) -> bool: ...

class TokenKind:
    COMMENT: TokenKind

class AccessSpecifier:
    PUBLIC: AccessSpecifier
    @property
    def name(self) -> str: ...

class LinkageKind:
    INTERNAL: LinkageKind

class File:
    @property
    def name(self) -> str: ...

class SourceLocation:
    @property
    def file(self) -> File | None: ...
    @property
    def line(self) -> int: ...
    @property
    def column(self) -> int: ...
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
    def kind(self) -> TokenKind: ...
    @property
    def extent(self) -> SourceRange: ...

class Type:
    @property
    def spelling(self) -> str: ...
    def get_canonical(self) -> Type: ...
    def get_num_template_arguments(self) -> int: ...
    def get_template_argument_type(self, num: int) -> Type: ...
    def get_declaration(self) -> Cursor: ...

class Cursor:
    @property
    def kind(self) -> CursorKind: ...
    @property
    def spelling(self) -> str: ...
    @property
    def displayname(self) -> str: ...
    @property
    def type(self) -> Type: ...
    @property
    def semantic_parent(self) -> Cursor | None: ...
    @property
    def location(self) -> SourceLocation: ...
    @property
    def extent(self) -> SourceRange: ...
    @property
    def linkage(self) -> LinkageKind: ...
    def get_children(self) -> Iterator[Cursor]: ...
    def walk_preorder(self) -> Iterator[Cursor]: ...
    def get_tokens(self) -> Iterator[Token]: ...
    def is_definition(self) -> bool: ...
    def get_num_template_arguments(self) -> int: ...
    def get_template_argument_type(self, num: int) -> Type: ...
    @property
    def referenced(self) -> Cursor | None: ...
    def is_default_method(self) -> bool: ...
    def is_default_constructor(self) -> bool: ...
    def is_copy_constructor(self) -> bool: ...
    def is_move_constructor(self) -> bool: ...
    def is_deleted_method(self) -> bool: ...
    def is_copy_assignment_operator_method(self) -> bool: ...
    def is_move_assignment_operator_method(self) -> bool: ...
    def get_arguments(self) -> Iterator[Cursor]: ...
    def get_definition(self) -> Cursor | None: ...
    @property
    def access_specifier(self) -> AccessSpecifier: ...
    @property
    def underlying_typedef_type(self) -> Type: ...

class _Lib:
    def clang_getNumOverloadedDecls(self, cursor: Cursor) -> int: ...  # noqa: N802 (libclang's name)
    def clang_getOverloadedDecl(self, cursor: Cursor, index: int) -> Cursor: ...  # noqa: N802
    def clang_getSpecializedCursorTemplate(self, cursor: Cursor) -> Cursor | None: ...  # noqa: N802

class _Conf:
    lib: _Lib

conf: _Conf

class Config:
    loaded: bool
    @staticmethod
    def set_library_file(filename: str) -> None: ...

class Diagnostic:
    Error: int
    @property
    def severity(self) -> int: ...
    @property
    def spelling(self) -> str: ...

class TranslationUnit:
    PARSE_SKIP_FUNCTION_BODIES: int
    @property
    def cursor(self) -> Cursor: ...
    @property
    def diagnostics(self) -> Iterator[Diagnostic]: ...

class TranslationUnitLoadError(Exception): ...

class Index:
    @staticmethod
    def create() -> Index: ...
    def parse(
        self,
        path: str,
        args: list[str] | None = None,
        unsaved_files: list[tuple[str, str]] | None = None,
        options: int = 0,
    ) -> TranslationUnit: ...
