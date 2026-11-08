defmodule Notice do
  def format(:absent), do: "setting unavailable"
  def format(key), do: Atom.to_string(key)
end
