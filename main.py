import graphviz
from tensor import Variable, Product, Function
from functions import frobenius2
from serializers.to_graphviz import to_graphviz
from serializers.to_tikz import to_tikz
from serializers.to_d3 import to_d3
from serializers.to_pytorch import to_pytorch


def main0():
    x = Variable("x", ["i"])
    y = Variable("y", ["i"])
    prod = x @ y

    prod.to_graphviz(g := graphviz.Graph())
    g.view()


def main1():
    x = Variable("x", ["i"])
    A = Variable("A", ["i", "o"])
    prod = A @ x

    prod.to_graphviz(g := graphviz.Graph())
    g.view()


def main(mode):
    # ||Ax - y||_2^2
    x = Variable("x", ["x"])
    y = Variable("y", ["y"])
    A = Variable("A", ["x", "y"])
    Axmy = A @ x - y
    F = frobenius2(Axmy)
    grad = F.grad(x)
    assert grad.edges == ["x'"]

    out = grad.simplify()
    print(f"{out=}")

    if mode == "graphviz":
        to_graphviz(out).view()
        print(to_graphviz(out).source)
    if mode == "tikz":
        latex_code = to_tikz(out)
        print(latex_code)
        compile_latex(latex_code)
    if mode == "d3":
        html_code = to_d3(out)
        with open("output.html", "w") as file:
            file.write(html_code)


def compile_latex(latex_code):
    import os, subprocess

    output_dir = "output_files"
    os.makedirs(output_dir, exist_ok=True)

    # Save the LaTeX code to a file in the output directory
    with open(os.path.join(output_dir, "output.tex"), "w") as file:
        file.write(latex_code)

    # Compile the LaTeX file using pdflatex with the -output-directory option
    subprocess.run(
        [
            # "pdflatex",
            "lualatex",
            "-output-directory",
            output_dir,
            os.path.join(output_dir, "output.tex"),
        ],
        check=True,
    )


def main2(mode):
    # ||Ax - y||_2^2
    x = Variable("x", ["x"])
    y = Variable("y", ["y"])
    A = Variable("A", ["x", "y"])
    F = frobenius2(A @ x - y)
    grad = F.grad(x).grad(x).simplify()
    assert grad.edges == ["x'", "x''"]

    if mode == "tikz":
        latex_code = to_tikz(grad)
        compile_latex(latex_code)


def main3(mode):
    # ||Ax - y||_2^2
    X = Variable("X", ["b", "x"])
    Y = Variable("Y", ["b", "y"])
    W = Variable("W", ["x", "y"])
    F = frobenius2(W @ X - Y)
    grad = F.grad(W).simplify()
    assert set(grad.edges) == {"x'", "y'"}

    if mode == "tikz":
        latex_code = to_tikz(grad)
        compile_latex(latex_code)

    print(to_pytorch(grad))



def main4(mode):
    # ||Ax - y||_2^2
    X = Variable("X", ["b", "x"])
    Y = Variable("Y", ["b", "y"])
    W = Variable("W", ["x", "y"])
    b = Variable("b", ["y"])
    F = frobenius2(W @ X + b - Y)
    grad = F.grad(b).simplify()

    if mode == "tikz":
        latex_code = to_tikz(grad)
        compile_latex(latex_code)

    print(to_pytorch(grad))


def main5(mode):
    # f(v(x))
    x = Variable("x", ["x"])
    v = Function("v", [x], ["x"], ["y"])
    f = Function("f", [v], ["y"], [])

    grad = f.grad(x).simplify()

    if mode == "tikz":
        print(grad)
        latex_code = to_tikz(grad)
        #print(f)
        #latex_code = to_tikz(f)
        for i, line in enumerate(latex_code.split("\n")):
            print(f"{i+1:2d} {line}")
        compile_latex(latex_code)

    print(to_pytorch(grad))

if __name__ == "__main__":
    import sys

    mode = sys.argv[1]
    main5(mode)
