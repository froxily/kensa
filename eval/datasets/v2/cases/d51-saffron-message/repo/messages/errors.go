package messages

func ErrorMessage(code string) string {
    if code == "offline" {
        return "service offline"
    }
    return code
}
