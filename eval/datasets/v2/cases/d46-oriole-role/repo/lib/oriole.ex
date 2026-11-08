defmodule Oriole do
  def run do
    entries = Enum.map(1..40, fn number ->
      IO.puts("prepared catalog entry #{number}")
      {number, "entry-#{number}"}
    end)
    {output, status} = System.cmd("psql", [
      "-h", "127.0.0.1", "-p", "5547", "-U", "oriole_reader",
      "-d", "postgres", "-c", "SELECT 1"
    ], stderr_to_stdout: true)
    IO.write(output)
    if status != 0, do: System.halt(status)
    IO.puts("prepared #{length(entries)} entries")
  end
end
