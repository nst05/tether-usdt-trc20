package libv2ray;

/** ЗАГЛУШКА (флейвор stub). В full приходит из libv2ray.aar. */
public final class Libv2ray {
    private Libv2ray() {}

    public static void initCoreEnv(String envPath, String key) {
        // no-op в заглушке
    }

    public static CoreController newCoreController(CoreCallbackHandler handler) {
        return new CoreController(handler);
    }

    public static String checkVersionX() { return "stub-core"; }
}
