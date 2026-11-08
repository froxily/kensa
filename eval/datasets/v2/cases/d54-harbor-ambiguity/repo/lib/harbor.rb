module Harbor
  def self.ready?(path)
    File.read(path).strip == "open"
  rescue Errno::ENOENT, Errno::EACCES
    false
  end
end
