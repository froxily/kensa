defmodule Finch do
  def run do
    entries = Enum.map(1..20, fn n ->
      IO.puts("prepared cache entry #{n}")
      {"entry:#{n}", Integer.to_string(n)}
    end)
    port = System.fetch_env!("FINCH_CACHE_PORT") |> String.to_integer()
    case :gen_tcp.connect(~c"127.0.0.1", port, [:binary, active: false], 2_000) do
      {:ok, socket} ->
        Enum.each(entries, fn {key, value} ->
          :gen_tcp.send(socket, ["SET ", key, " ", value, "\r\n"])
        end)
        :gen_tcp.close(socket)
        IO.puts("cache ready")
      {:error, reason} ->
        IO.puts(:stderr, "cache connection: #{inspect(reason)}")
        IO.puts(:stderr, "warmup failed")
        System.halt(1)
    end
  end
end
