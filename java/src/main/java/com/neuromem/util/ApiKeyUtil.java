package com.neuromem.util;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

/**
 * Utility class for API key generation and hashing.
 */
public class ApiKeyUtil {

    private static final String API_KEY_PREFIX = "nm_";
    private static final int KEY_LENGTH = 32;
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    /**
     * Generate a new API key with nm_ prefix.
     *
     * @return Generated API key (e.g., nm_abc123...)
     */
    public static String generateApiKey() {
        byte[] randomBytes = new byte[KEY_LENGTH];
        SECURE_RANDOM.nextBytes(randomBytes);
        String encoded = Base64.getUrlEncoder().withoutPadding().encodeToString(randomBytes);
        return API_KEY_PREFIX + encoded;
    }

    /**
     * Hash an API key using SHA-256.
     *
     * @param apiKey The API key to hash
     * @return SHA-256 hash of the API key
     */
    public static String hashApiKey(String apiKey) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(apiKey.getBytes(StandardCharsets.UTF_8));
            return bytesToHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException("SHA-256 algorithm not found", e);
        }
    }

    /**
     * Get the prefix of an API key (first 7 characters after nm_).
     * Used for key lookup optimization.
     *
     * @param apiKey The API key
     * @return Key prefix (e.g., nm_abc1)
     */
    public static String getKeyPrefix(String apiKey) {
        if (apiKey == null || apiKey.length() < 7) {
            return "";
        }
        return apiKey.substring(0, Math.min(7, apiKey.length()));
    }

    /**
     * Convert byte array to hex string.
     */
    private static String bytesToHex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
    }
}
