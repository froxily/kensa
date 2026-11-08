public final class LabelPolicy {
    public static String clean(String value) { return value.trim(); }

    public static String fromEnvironment() {
        String label = System.getenv("PARSLEY_ARCHIVE_LABEL");
        if (label == null || label.isBlank()) {
            throw new IllegalStateException("PARSLEY_ARCHIVE_LABEL is required");
        }
        return clean(label);
    }
}
