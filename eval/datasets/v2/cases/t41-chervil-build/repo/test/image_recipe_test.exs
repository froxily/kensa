defmodule ImageRecipeTest do
  use ExUnit.Case

  test "recipe builds a relay image" do
    {output, status} = System.cmd("docker", ["build", "--progress=plain", "-t", "chervil-relay", "-f", "Probe.Dockerfile", "."], stderr_to_stdout: true)
    IO.write(output)
    assert status == 0
  end
end
