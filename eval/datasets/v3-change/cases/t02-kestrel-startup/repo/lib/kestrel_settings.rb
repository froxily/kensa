module KestrelSettings
  REGION = ENV.fetch("KESTREL_REGION")

  def self.banner
    "region: #{REGION}"
  end
end
