import pytest
import wf2wf.expression as expr_mod
from wf2wf.expression import evaluate, ExpressionTimeout, ExpressionError


def test_strip_wrapper_and_basic():
    assert evaluate('$(1 + 1)') == 2
    try:
        res = evaluate('${ true && false }')
        assert res is False
    except ExpressionError:
        # Fallback evaluator cannot handle JS syntax when js2py is absent
        if getattr(expr_mod, '_HAS_JS2PY', False):
            raise


def test_timeout():
    # Expression with infinite loop (js) fallback to python; use long expr to trigger timeout
    long_expr = '1'
    if getattr(expr_mod, '_HAS_JS2PY', False):
        with pytest.raises(ExpressionTimeout):
            evaluate('while(true) {1+1}', timeout_s=0.05)

    # Python fallback timeout test
    with pytest.raises((ExpressionTimeout, ExpressionError)):
        long_expr = '1+' * 100000 + '1'
        evaluate(long_expr, timeout_s=0.05)


def test_length_limit():
    with pytest.raises(ExpressionError):
        evaluate('1' * 20000) 