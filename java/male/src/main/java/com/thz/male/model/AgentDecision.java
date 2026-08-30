package com.thz.male.model;

public record AgentDecision(
        String argument,
        String status,
        String vote,
        String questionTo,
        String reasoning) {
    public AgentDecision {
        if (status == null)
            status = "CONTINUE";
        if (vote == null)
            vote = "abstain";
    }
}
