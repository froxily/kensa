require 'net/http'
require 'uri'

$stdout.sync = true
base = 'https://api.github.com/repos/calendula-labs/build-plan/actions/workflows'
headers = {'Authorization' => "Bearer #{ENV.fetch('CALENDULA_TOKEN')}", 'Accept' => 'application/vnd.github+json'}
(1..20).each do |page|
  res = Net::HTTP.get_response(URI("#{base}?per_page=1&page=#{page}"), headers)
  puts "workflow page #{page}: HTTP #{res.code}"
  abort 'workflow listing failed' unless res.is_a?(Net::HTTPSuccess)
end
uri = URI("#{base}/dispatch-check.yml/dispatches")
request = Net::HTTP::Post.new(uri, headers.merge('Content-Type' => 'application/json'))
request.body = File.read('settings/dispatch-body.json')
response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http| http.request(request) }
unless response.is_a?(Net::HTTPSuccess)
  warn "dispatch HTTP #{response.code}: #{response.body}"
  warn File.read('reports/dispatch-response.json')
  exit 1
end
