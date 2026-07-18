package libv2ray;

/** ЗАГЛУШКА (флейвор stub). В full приходит из libv2ray.aar. */
public final class Libv2ray {
    private Libv2ray() {}

    public static void initV2Env(String assetPath, String deviceId) {
        // no-op в заглушке
    }

    public static V2RayPoint newV2RayPoint(V2RayVPNServiceSupportsSet supportSet, boolean forSpeedTest) {
        return new V2RayPoint(supportSet);
    }

    public static String checkVersionX() { return "stub-core"; }
}
