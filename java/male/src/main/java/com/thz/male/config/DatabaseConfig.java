package com.thz.male.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DatabaseConfig {

    @Value("${male.debate.max-turns:25}")
    private int maxTurns;

    @Value("${male.debate.min-turns:8}")
    private int minTurns;

    @Value("${male.debate.num-ctx:8192}")
    private int numCtx;

    @Value("${male.debate.consensus-threshold:5}")
    private int consensusThreshold;

    @Value("${male.debate.pause-between-seconds:300}")
    private int pauseBetweenSeconds;

    @Value("${male.session.duration-hours:8.0}")
    private double durationHours;

    @Value("${male.model.default:qwen2.5:7b}")
    private String defaultModel;

    public int getMaxTurns() {
        return maxTurns;
    }

    public int getMinTurns() {
        return minTurns;
    }

    public int getNumCtx() {
        return numCtx;
    }

    public int getConsensusThreshold() {
        return consensusThreshold;
    }

    public int getPauseBetweenSeconds() {
        return pauseBetweenSeconds;
    }

    public double getDurationHours() {
        return durationHours;
    }

    public String getDefaultModel() {
        return defaultModel;
    }
}
