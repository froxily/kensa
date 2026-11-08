defmodule MicaTest do
  use ExUnit.Case

  test "trims leading whitespace", do: assert(Mica.normalize(" a") == "a")
  test "trims trailing whitespace", do: assert(Mica.normalize("a ") == "a")
  test "keeps internal space", do: assert(Mica.normalize("a b") == "a b")
  test "handles empty input", do: assert(Mica.normalize("") == "")
  test "keeps digits", do: assert(Mica.normalize("42") == "42")
  test "handles tabs", do: assert(Mica.normalize("\tx") == "x")
  test "keeps case", do: assert(Mica.normalize("X") == "X")
  test "handles newline", do: assert(Mica.normalize("x\n") == "x")
  test "keeps punctuation", do: assert(Mica.normalize("a-b") == "a-b")
  test "loads namespace", do: assert(Mica.namespace() != "")
end
