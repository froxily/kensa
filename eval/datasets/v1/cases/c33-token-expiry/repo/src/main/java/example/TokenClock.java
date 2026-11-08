package example;

public final class TokenClock {
    private TokenClock() {}

    public static boolean isValid(long now, long expiresAt) {
        if (expiresAt < 0) {
            throw new IllegalArgumentException("negative expiry");
        }
        return now <= expiresAt;
    }
}
