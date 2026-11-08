require 'net/http'

$stdout.sync = true
File.foreach('jobs/shelves.list') { |line| puts "catalogued shelf: #{line.strip}" }
uri = URI('http://127.0.0.1:15984/_session')
response = Net::HTTP.post_form(uri, 'name' => 'demo_reader', 'password' => 'fake-incorrect-password')
puts "CouchDB session HTTP #{response.code} #{response.message}"
puts response.body
exit 1 unless response.is_a?(Net::HTTPSuccess)
