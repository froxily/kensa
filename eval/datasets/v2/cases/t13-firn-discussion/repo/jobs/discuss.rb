require "json"
require "net/http"

STDOUT.sync = true
topics = File.readlines("data/topics.list", chomp: true)
topics.each { |topic| puts "prepared topic #{topic}" }
query = <<~GRAPHQL
  mutation($id: ID!, $body: String!) {
    addDiscussionComment(input: {discussionId: $id, body: $body}) { comment { id } }
  }
GRAPHQL
uri = URI("https://api.github.com/graphql")
request = Net::HTTP::Post.new(uri)
request["Authorization"] = "Bearer #{ENV.fetch('FIRN_GRAPH_TOKEN')}"
request["Content-Type"] = "application/json"
request.body = JSON.generate(query: query, variables: {id: ENV.fetch("FIRN_DISCUSSION_ID"), body: topics.join(", ")})
response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http| http.request(request) }
puts "GraphQL HTTP #{response.code}"
result = JSON.parse(response.body)
if result["errors"]
  result["errors"].each { |error| warn "GraphQL error type: #{error.fetch('type', 'UNKNOWN')}" }
  warn "discussion update failed"
  exit 1
end
