Code.require_file("../lib/notice.ex", __DIR__)
ExUnit.start(trace: true, seed: 0)

defmodule NoticeTest do
  use ExUnit.Case

  test "formats amber", do: assert(Notice.format(:amber) == "amber")
  test "formats blue", do: assert(Notice.format(:blue) == "blue")
  test "formats coral", do: assert(Notice.format(:coral) == "coral")
  test "formats dusk", do: assert(Notice.format(:dusk) == "dusk")
  test "formats ecru", do: assert(Notice.format(:ecru) == "ecru")
  test "formats fern", do: assert(Notice.format(:fern) == "fern")
  test "formats gold", do: assert(Notice.format(:gold) == "gold")
  test "formats hazel", do: assert(Notice.format(:hazel) == "hazel")
  test "describes missing setting" do
    assert Notice.format(:absent) == "missing environment variable: FENNEL_POLICY"
  end
end
