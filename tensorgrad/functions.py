from typing import Any, Callable, Iterable, Union
import torch
from tensorgrad.tensor import Function, Ones, Tensor, Product, Copy, Zero, make_distinct
from math import factorial

# We mostly try to follow the behavior of pytorch's named tensors:
# https://pytorch.org/docs/stable/name_inference.html

# TODO:
# - Add all the functions of PyTorch
# - Add general function inverses, implicit functions
# - Taylor approximation


def frobenius2(t: Tensor) -> Tensor:
    return Product([t, t])


def einsum(tensors, output_edges):
    if len(output_edges) != len(set(output_edges)):
        # We don't support einsums like "i -> ii".
        # We also don't support "ii -> i", but that's more hidden, because the input tensors can't have double edges.
        raise ValueError("Output edges must be unique.")
    # Basically like Product, but will create some Identity's to ensure only the free_edges are free afterwards.
    all_free_edges = {e for t in tensors for e in t.edges}
    # TODO: We only really need to rename the free edges of each tensor, so `make_distinct`` is overkill.
    dis_tensors, renames = make_distinct(*tensors, used_names=all_free_edges)
    joins = []
    for e in all_free_edges:
        # We create a Copy([...]) with all the entries that have this edge
        edges = [rename[e] for rename in renames if e in rename]
        if e in output_edges:
            edges.append(e)
        joins.append(Copy(edges))
    return Product(dis_tensors + joins)


def kronecker(*tensors):
    # Basically just rename everything to be distinct, then contraction
    # Note: This function returns the tensor product, which is different from the
    #       Kronecker product as often described in the literature. To get the
    #       Kronecker product you have to flatten the output tensors.
    dis_tensors, _renames = make_distinct(*tensors)
    return Product(dis_tensors)


def diag(t: Tensor, new_edges: list[str]):
    """Takes vector `t` and creates a diagonal matrix with `t` on the diagonal."""
    if len(t.edges) != 1:
        raise ValueError("Expected a vector, got a tensor with more than one edge.")
    # If the vector's edge is in new_edges, we need to rename it
    (t,), _renames = make_distinct(t, used_names=new_edges)
    return Copy(new_edges + t.edges) @ t


def sum(tensor: Tensor, edges: list[str] = None, keepdims=False) -> Tensor:
    """Sum the tensor over the given dimensions."""
    edges = edges or tensor.edges
    out = Product([tensor] + [Copy([e]) for e in edges])
    if keepdims:
        return out @ Ones(edges)
    return out


def trace(tensor: Tensor) -> Tensor:
    return tensor @ Copy(tensor.edges)


# The common type of cuntion in ML is that of the broadcasted function.
# Say we have shape (B, N, M), we'll typically apply a function "along" axis M,
# which means it takes a vector as an input and outputs a vector.
# And we call it on each vector from (B, N).
#
# It would be cool to express functions such as max(dim=...) as a vector, meaning
# it would show up in the product graph as a node with a single edge, which connects
# to the axis "over which" we apply the function. This matches the intuition of an
# inner product with a vector along that axis, which ends up removing it.
#
# But in this framework, how would we express an elementwise function? It wouldn't have
# any edges to connect to.
class Elementwise(Function):
    def __init__(self, name: str, function: Callable, t: Tensor, derivative: Callable = None):
        # An element wise function takes no input edges and output no output edges
        # That makes it kinda difficult to visualize in a graph... Might just have to surround it
        super().__init__(name, [], (t,))
        self.function = function
        self.derivative = derivative

    def inner_grad(self, i, new_edges) -> Tensor:
        # print("inner_grad", self.tensors[0].edges, new_edges)
        assert len(new_edges) == 0, "Elementwise functions don't have input edges"
        t = self.derivative(self.tensors[0])
        return t

    def update_edge_dims(self, shapes: dict[int, dict[str, int]]) -> Iterable[tuple[Tensor, str, int]]:
        t = self.tensors[0]
        union = shapes.get(id(self), {}) | shapes.get(id(t), {})
        for e in t.edges:
            if e in union:
                yield t, e, union[e]
                yield self, e, union[e]

    def __call__(self, value: torch.tensor) -> torch.tensor:
        return self.function(value)

    def simplify(self, args: dict[str, Any] = {}):
        # TODO: Functions like pow(x, -1) can commute with products. Do we want to do that?
        # And of course logs creating sums etc.
        return Elementwise(self.name, self.function, self.tensors[0].simplify(args=args), self.derivative)

    def rename(self, kwargs: dict[str, str]):
        # It's fine to do a full rename of self.tensor[0], since all its edges are external/broadcasted
        return Elementwise(self.name, self.function, self.tensors[0].rename(kwargs), self.derivative)


def log(t: Tensor) -> Tensor:
    return Elementwise("log", torch.log, t, lambda t: pow(t, -1))


def exp(t: Tensor) -> Tensor:
    # The derivative function (last) can't just reuse the same tensor t as we got,
    # since it may have been renamed since then.
    return Elementwise("exp", torch.exp, t, lambda t: exp(t))


def pow(tensor: Tensor, k: int) -> Tensor:
    """Elementwise t^k"""
    if k == 0:
        return Ones(tensor.edges)
    return Elementwise(
        f"pow({k})",
        lambda x: torch.pow(x, k),
        tensor,
        lambda tensor: k * pow(tensor, k - 1),
    )


def softmax(t: Tensor, dims: list[str]) -> Tensor:
    if set(dims) - set(t.edges):
        raise ValueError("dims must be a subset of t.edges")
    e = exp(t)
    return e * pow(sum(e, dims, keepdims=True), -1)


def cross_entropy(t: Tensor, y: Tensor, dims: list[str]) -> Tensor:
    if set(dims) - set(t.edges):
        raise ValueError("dims must be a subset of t.edges")
    return -sum(y * log(softmax(t, dims)), dims)


def gt(x: Tensor, y: Tensor) -> Tensor:
    """Returns a tensor that's 1 where x >= y, 0 otherwise."""

    class Gt(Function):
        def inner_grad(self, i, new_edges) -> Tensor:
            return Zero(self.edges + new_edges)

        def __call__(self, xt: torch.tensor, yt: torch.tensor) -> torch.tensor:
            return xt >= yt


def max(t: Tensor, dims: list[str]) -> Tensor:
    class Max(Function):
        def __init__(self, function: Callable, t: Tensor):
            super().__init__("max", [], (t,))
            self.function = function

        def inner_grad(self, i, new_edges) -> Tensor:
            t = self.derivative(self.tensors[0])
            return t

        def update_edge_dims(self, shapes: dict[int, dict[str, int]]) -> Iterable[tuple[Tensor, str, int]]:
            # If this is mostly related to broadcasting, maybe I can just put it into the Function class?
            t = self.tensors[0]
            union = shapes.get(id(self), {}) | shapes.get(id(t), {})
            for e in t.edges:
                if e in union:
                    yield t, e, union[e]
                    yield self, e, union[e]

        def __call__(self, value: torch.tensor) -> torch.tensor:
            return self.function(value)

        def simplify(self, args: dict[str, Any] = {}):
            # The reason we need to override this is that it's creating a new instance of the function,
            # and the parent class doesn't know about the function attribute.
            return Elementwise(self.name, self.function, self.tensors[0].simplify(args=args), self.derivative)

        def rename(self, kwargs: dict[str, str]):
            return Elementwise(self.name, self.function, self.tensors[0].rename(kwargs), self.derivative)

    raise NotImplementedError


# Some questions:
# - Who's responsible for realizing that 1/x and x cancel out?
#   - Maybe tensors can register simplification rules
# - How do we get names for the derivatives?
# - Should functions be forced to output the right edge names?
# - What really is going on with multiple inputs?
