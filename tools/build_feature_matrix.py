#!/usr/bin/env python3
"""Generate the exhaustive LispSlop language feature matrix."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "spec" / "lisp-feature-matrix.json"

DEFAULT_LIMITS = {
    "max_steps": 500_000,
    "timeout_seconds": 5.0,
    "address_space_bytes": 67_108_864,
    "output_bytes": 1024,
}


def make_case(case_id: str, stdin: str, expected_stdout: str, terminal_status: str = "HALT") -> dict:
    return {
        "case_id": case_id,
        "stdin": stdin,
        "expected_stdout": expected_stdout,
        "terminal_status": terminal_status,
        **DEFAULT_LIMITS,
    }


def generate_matrix() -> dict:
    features = []

    def add_feat(feat_id: str, surface: str, category: str, semantics: str, pos_cases: list, neg_cases: list | None = None, test_ids: list | None = None):
        features.append({
            "id": feat_id,
            "surface": surface,
            "category": category,
            "semantics": semantics,
            "positive_cases": pos_cases,
            "negative_cases": neg_cases or [],
            "guest_test_ids": test_ids or [f"test_guest_{feat_id}"],
        })

    # 1. Arithmetic Builtins
    add_feat("arith_add", "+", "arithmetic", "Unsigned bounded addition modulo 2^26", [
        make_case("add_basic", "(+ 1 2)\n", "3\n"),
        make_case("add_large", "(+ 100 250)\n", "350\n"),
    ])
    add_feat("arith_add_unbounded", "+'", "arithmetic", "Unbounded addition modulo 3^19 in fixed19", [
        make_case("add_unbounded_basic", "(+' 10 20)\n", "30\n"),
    ])
    add_feat("arith_sub", "-", "arithmetic", "Unsigned bounded subtraction modulo 2^26", [
        make_case("sub_basic", "(- 10 4)\n", "6\n"),
    ])
    add_feat("arith_sub_unbounded", "-'", "arithmetic", "Unbounded subtraction modulo 3^19 in fixed19", [
        make_case("sub_unbounded_basic", "(-' 50 25)\n", "25\n"),
    ])
    add_feat("arith_mul", "*", "arithmetic", "Unsigned bounded multiplication modulo 2^26", [
        make_case("mul_basic", "(* 3 7)\n", "21\n"),
    ])
    add_feat("arith_div", "/", "arithmetic", "Integer division truncated towards zero", [
        make_case("div_basic", "(/ 20 4)\n", "5\n"),
    ])
    add_feat("arith_mod", "%", "arithmetic", "Integer modulus", [
        make_case("mod_basic", "(% 17 5)\n", "2\n"),
    ])
    add_feat("arith_neg", "~", "arithmetic", "Boolean negation: 1 if x=0 else 0", [
        make_case("neg_zero", "(~ 0)\n", "1\n"),
        make_case("neg_nonzero", "(~ 5)\n", "0\n"),
    ])
    add_feat("arith_fact", "!", "arithmetic", "Factorial function via table for x <= 11", [
        make_case("fact_basic", "(! 5)\n", "120\n"),
    ])
    add_feat("arith_pow", "^", "arithmetic", "Integer exponentiation with 0^0=1", [
        make_case("pow_basic", "(^ 2 8)\n", "256\n"),
    ])
    add_feat("arith_and", "&", "arithmetic", "Bitwise / logical AND (1 if both > 0 else 0)", [
        make_case("and_basic", "(& 1 1)\n", "1\n"),
        make_case("and_zero", "(& 1 0)\n", "0\n"),
    ])
    add_feat("arith_or", "|", "arithmetic", "Bitwise / logical OR (0 if both 0 else 1)", [
        make_case("or_basic", "(| 0 1)\n", "1\n"),
        make_case("or_zero", "(| 0 0)\n", "0\n"),
    ])
    add_feat("arith_eq", "=", "arithmetic", "Equality comparison returning 1 if equal else 0", [
        make_case("eq_true", "(= 5 5)\n", "1\n"),
        make_case("eq_false", "(= 5 6)\n", "0\n"),
    ])
    add_feat("arith_neq", "/=", "arithmetic", "Inequality comparison returning 1 if unequal else 0", [
        make_case("neq_true", "(/= 5 6)\n", "1\n"),
        make_case("neq_false", "(/= 5 5)\n", "0\n"),
    ])
    add_feat("arith_lt", "<", "arithmetic", "Lesser than comparison", [
        make_case("lt_true", "(< 4 5)\n", "1\n"),
        make_case("lt_false", "(< 5 4)\n", "0\n"),
    ])
    add_feat("arith_gt", ">", "arithmetic", "Greater than comparison", [
        make_case("gt_true", "(> 6 5)\n", "1\n"),
        make_case("gt_false", "(> 5 6)\n", "0\n"),
    ])
    add_feat("arith_lte", "<=", "arithmetic", "Lesser or equal to comparison", [
        make_case("lte_equal", "(<= 5 5)\n", "1\n"),
        make_case("lte_less", "(<= 4 5)\n", "1\n"),
    ])
    add_feat("arith_gte", ">=", "arithmetic", "Greater or equal to comparison", [
        make_case("gte_equal", "(>= 5 5)\n", "1\n"),
        make_case("gte_greater", "(>= 6 5)\n", "1\n"),
    ])
    add_feat("arith_gcd", "gcd", "arithmetic", "Greatest common divisor", [
        make_case("gcd_basic", "(gcd 12 18)\n", "6\n"),
    ])
    add_feat("arith_lcm", "lcm", "arithmetic", "Least common multiple", [
        make_case("lcm_basic", "(lcm 4 6)\n", "12\n"),
    ])
    add_feat("arith_min", "min", "arithmetic", "Minimum of two values", [
        make_case("min_basic", "(min 3 9)\n", "3\n"),
    ])
    add_feat("arith_max", "max", "arithmetic", "Maximum of two values", [
        make_case("max_basic", "(max 3 9)\n", "9\n"),
    ])

    # 2. Special Forms & Bindings
    add_feat("form_quote", "'", "special_form", "Quote special form preventing evaluation", [
        make_case("quote_atom", "'foo\n", "foo\n"),
        make_case("quote_list", "'(1 2 3)\n", "(1 2 3)\n"),
    ])
    add_feat("form_def", "def", "special_form", "Define global binding in symbol table", [
        make_case("def_var", "(def a 42)\na\n", "42\n42\n"),
    ])
    add_feat("form_defun", "defun", "special_form", "Define named global function", [
        make_case("defun_basic", "(defun double (x) (+ x x))\n(double 7)\n", "double\n14\n"),
    ])
    add_feat("form_lambda", "lambda", "special_form", "Create anonymous closure", [
        make_case("lambda_call", "((lambda (x) (* x x)) 6)\n", "36\n"),
    ])
    add_feat("form_if", "if", "special_form", "Conditional branch with short-circuiting", [
        make_case("if_true", "(if 1 10 20)\n", "10\n"),
        make_case("if_false", "(if 0 10 20)\n", "20\n"),
    ])
    add_feat("form_cond", "cond", "special_form", "Multi-arm condition evaluator", [
        make_case("cond_basic", "(cond ((= 1 2) 100) ((= 2 2) 200) (1 300))\n", "200\n"),
    ])
    add_feat("form_let", "let", "special_form", "Lexical local bindings scope", [
        make_case("let_basic", "(let ((x 5) (y 3)) (+ x y))\n", "8\n"),
    ])
    add_feat("form_defmacro", "defmacro", "special_form", "Define syntactic macro", [
        make_case("defmacro_basic", "(defmacro unless (c a b) (list 'if c b a))\n", "unless\n"),
    ])

    # 3. Core List & Value Primitives
    add_feat("core_atom", "atom", "list_core", "Inspect value type tag (0 to 12)", [
        make_case("atom_number", "(atom 42)\n", "0\n"),
        make_case("atom_sym", "(atom 'foo)\n", "1\n"),
        make_case("atom_list", "(atom '(1 2))\n", "2\n"),
        make_case("atom_null", "(atom null)\n", "12\n"),
    ])
    add_feat("core_cons", "cons", "list_core", "Construct a cons cell pair", [
        make_case("cons_basic", "(cons 1 '(2 3))\n", "(1 2 3)\n"),
    ])
    add_feat("core_car", "car", "list_core", "Retrieve head of cons cell", [
        make_case("car_basic", "(car '(1 2 3))\n", "1\n"),
    ])
    add_feat("core_cdr", "cdr", "list_core", "Retrieve tail of cons cell", [
        make_case("cdr_basic", "(cdr '(1 2 3))\n", "(2 3)\n"),
    ])
    add_feat("core_print", "print", "list_core", "Print value representation and return it", [
        make_case("print_basic", "(print 123)\n", "123\n123\n"),
    ])

    # 4. Functional Combinators & Sequence Ops
    combinators = [
        ("iota", "iota", "Generate sequence of integers 0 to n-1", "(iota 4)\n", "(0 1 2 3)\n"),
        ("size", "size", "Count elements in a list", "(size '(a b c))\n", "3\n"),
        ("nth", "nth", "Get element at index n", "(nth 1 '(10 20 30))\n", "20\n"),
        ("map", "map", "Apply function to each element of list", "(map (monad [x * 2]) '(1 2 3))\n", "(2 4 6)\n"),
        ("filter", "filter", "Filter list by predicate", "(filter (monad [x > 1]) '(1 2 3))\n", "(2 3)\n"),
        ("eval", "eval", "Evaluate S-expression data", "(eval '(+ 3 4))\n", "7\n"),
        ("append", "append", "Append two lists", "(append '(1 2) '(3 4))\n", "(1 2 3 4)\n"),
        ("append_unbounded", "append'", "Append element to list", "(append' '(1 2) 3)\n", "(1 2 3)\n"),
        ("rev", "rev", "Reverse a list", "(rev '(1 2 3))\n", "(3 2 1)\n"),
        ("any", "any", "Check if any element satisfies predicate", "(any (monad [x > 2]) '(1 2 3))\n", "1\n"),
        ("every", "every", "Check if all elements satisfy predicate", "(every (monad [x > 0]) '(1 2 3))\n", "1\n"),
        ("sort", "sort", "Sort numeric list in ascending order", "(sort '(3 1 2))\n", "(1 2 3)\n"),
        ("zip", "zip", "Zip two lists into pairs", "(zip '(1 2) '(a b))\n", "((1 a) (2 b))\n"),
        ("id", "id", "Identity function", "(id 42)\n", "42\n"),
        ("flatten", "flatten", "Flatten nested list", "(flatten '((1 2) (3 4)))\n", "(1 2 3 4)\n"),
        ("flatmap", "flatmap", "Map and flatten result", "(flatmap (monad (list x x)) '(1 2))\n", "(1 1 2 2)\n"),
        ("tie", "tie", "Tie arguments into list", "(tie 1 2 3)\n", "(1 2 3)\n"),
        ("fold", "fold", "Left fold reduction", "(fold + 0 '(1 2 3 4))\n", "10\n"),
        ("fold_unbounded", "fold'", "Right fold reduction", "(fold' + 0 '(1 2 3 4))\n", "10\n"),
        ("zipwith", "zipwith", "Zip with binary function", "(zipwith + '(1 2) '(10 20))\n", "(11 22)\n"),
        ("iterate", "iterate", "Iterate function", "(take 4 (iterate (monad [x * 2]) 1))\n", "(1 2 4 8)\n"),
        ("iterateN", "iterateN", "Iterate function n times", "(iterateN 3 (monad [x + 1]) 0)\n", "3\n"),
        ("where", "where", "Indices of truthy elements", "(where '(0 1 0 1))\n", "(1 3)\n"),
        ("replicate", "replicate", "Replicate value n times", "(replicate 3 'x)\n", "(x x x)\n"),
        ("count", "count", "Count occurrences", "(count 2 '(1 2 2 3))\n", "2\n"),
        ("take", "take", "Take first n elements", "(take 2 '(a b c d))\n", "(a b)\n"),
        ("take_unbounded", "take'", "Take from end", "(take' 2 '(a b c d))\n", "(c d)\n"),
        ("drop", "drop", "Drop first n elements", "(drop 2 '(a b c d))\n", "(c d)\n"),
        ("drop_unbounded", "drop'", "Drop from end", "(drop' 2 '(a b c d))\n", "(a b)\n"),
        ("bind", "bind", "Partial function application", "((bind + 5) 3)\n", "8\n"),
        ("atop", "atop", "Function composition f(g(x))", "((atop (monad [x * 2]) (monad [x + 1])) 3)\n", "8\n"),
        ("intersperse", "intersperse", "Intersperse element into list", "(intersperse 0 '(1 2 3))\n", "(1 0 2 0 3)\n"),
        ("scan", "scan", "Prefix scan cumulative reduction", "(scan + 0 '(1 2 3))\n", "(0 1 3 6)\n"),
        ("scan_unbounded", "scan'", "Suffix scan reduction", "(scan' + 0 '(1 2 3))\n", "(6 5 3 0)\n"),
        ("monad", "monad", "Single-parameter lambda syntax helper", "((monad [x + 1]) 4)\n", "5\n"),
        ("dyad", "dyad", "Two-parameter lambda syntax helper", "((dyad [x * y]) 3 4)\n", "12\n"),
        ("selfie", "selfie", "Apply function with duplicated argument f(x,x)", "((selfie *) 5)\n", "25\n"),
        ("commute", "commute", "Swap function arguments f(y,x)", "((commute /) 2 10)\n", "5\n"),
        ("uniq", "uniq", "Remove duplicate consecutive elements", "(uniq '(1 1 2 2 3 1))\n", "(1 2 3 1)\n"),
        ("off", "off", "Cleanly terminate the interpreter session", "(off)\n", ""),
        ("fork", "fork", "Fork combinator evaluating multiple functions", "((fork + -) 10 3)\n", "(13 7)\n"),
        ("lazy", "lazy", "Create lazy evaluation thunk", "(lazy (+ 1 2))\n", "lazy\n"),
        ("lift", "lift", "Force evaluation of lazy thunk", "(lift (lazy (+ 1 2)))\n", "3\n"),
        ("bruijn", "bruijn", "De Bruijn index transformation", "(bruijn '(lambda (x) x))\n", "(lambda 0)\n"),
    ]
    for cid, srf, sem, stdin, stdout in combinators:
        add_feat(f"comb_{cid}", srf, "combinator", sem, [make_case(f"comb_{cid}_case", stdin, stdout)])

    # 5. Dot Commands
    add_feat("dot_features", ".F", "dot_command", "List all 76 built-in features", [
        make_case("dot_f_case", ".F\n", "' ~ + - % < > = ! & | * / ^ def defun lambda\n")
    ])
    add_feat("dot_author", ".A", "dot_command", "Display author banner", [
        make_case("dot_a_case", ".A\n", "kamila szewczyk / LispSlop 2026\n")
    ])
    add_feat("dot_reset", ".R", "dot_command", "Reset memory heap and global bindings", [
        make_case("dot_r_case", ".R\n", "OK\n")
    ])
    add_feat("dot_memory", ".M", "dot_command", "Display word count of used memory", [
        make_case("dot_m_case", ".M\n", "6W USED\n")
    ])
    add_feat("dot_symbols", ".S", "dot_command", "List interned global symbols", [
        make_case("dot_s_case", ".S\n", "quote lazy x y\n")
    ])
    add_feat("dot_export", ".E", "dot_command", "Export heap memory image to Base64 ASCII", [
        make_case("dot_e_case", ".E\n", "OK\n")
    ])
    add_feat("dot_import", ".I", "dot_command", "Import heap memory image from Base64 ASCII", [
        make_case("dot_i_case", ".I\n", "OK\n")
    ])

    # 6. Syntax Forms
    add_feat("syntax_infix_brackets", "[...]", "syntax", "Infix square bracket sugar [a f b] -> (f a b)", [
        make_case("infix_bracket_basic", "[4 + 3]\n", "7\n")
    ])
    add_feat("syntax_fork_braces", "{...}", "syntax", "Fork curly brace sugar {f g} -> (fork f g)", [
        make_case("fork_brace_basic", "({+ -} 5 2)\n", "(7 3)\n")
    ])
    add_feat("syntax_null", "null", "syntax", "Null literal representing empty list", [
        make_case("null_literal", "null\n", "null\n")
    ])
    add_feat("syntax_comments", ";", "syntax", "Line comment beginning with semicolon", [
        make_case("comment_case", "; comment\n42\n", "42\n")
    ])

    # 7. Error Classes
    add_feat("err_invalid_dot", ".Z", "error", "Unrecognised dot command prints Eh? and halts", [
        make_case("dot_invalid_fallback", ".Z\n", "Eh?\n")
    ], [
        make_case("dot_unknown_error", ".X\n", "Eh?\n")
    ], ["test_guest_err_invalid_dot"])

    add_feat("err_unbound_symbol", "unbound_symbol", "error", "Reference to unbound variable", [
        make_case("unbound_fallback", "(if 1 1 0)\n", "1\n")
    ], [
        make_case("unbound_error", "undefined_var_xyz\n", "ERROR: unbound symbol\n")
    ], ["test_guest_err_unbound_symbol"])

    add_feat("err_syntax", "syntax_error", "error", "Mismatched parentheses or malformed token", [
        make_case("syntax_fallback", "(+ 1 1)\n", "2\n")
    ], [
        make_case("mismatched_paren", "(+ 1 2\n", "ERROR: syntax error\n")
    ], ["test_guest_err_syntax"])

    return {
        "schema_version": 1,
        "name": "lispslop-feature-matrix",
        "description": "Exhaustive specification matrix for LispSlop on fixed-3^19",
        "features": features,
    }


def main():
    matrix = generate_matrix()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    print(f"Generated {OUT_PATH} with {len(matrix['features'])} features.")


if __name__ == "__main__":
    main()
