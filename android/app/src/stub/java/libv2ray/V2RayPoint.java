package libv2ray;

/** ЗАГЛУШКА (флейвор stub). В full приходит из libv2ray.aar. */
public class V2RayPoint {
    private String configureFileContent = "";
    private String domainName = "";
    private boolean running = false;
    private final V2RayVPNServiceSupportsSet supportSet;

    public V2RayPoint(V2RayVPNServiceSupportsSet supportSet) {
        this.supportSet = supportSet;
    }

    public String getConfigureFileContent() { return configureFileContent; }
    public void setConfigureFileContent(String v) { this.configureFileContent = v; }

    public String getDomainName() { return domainName; }
    public void setDomainName(String v) { this.domainName = v; }

    public boolean getIsRunning() { return running; }

    public void runLoop(boolean prefIpv6) {
        running = true;
        if (supportSet != null) {
            try {
                supportSet.setup("");
                supportSet.sendFd();
            } catch (Exception ignored) {
            }
        }
    }

    public void stopLoop() {
        running = false;
        if (supportSet != null) {
            try {
                supportSet.shutdown();
            } catch (Exception ignored) {
            }
        }
    }

    public long measureDelay() { return -1L; }
}
