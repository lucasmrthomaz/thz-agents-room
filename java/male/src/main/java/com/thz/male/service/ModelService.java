package com.thz.male.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.*;

@Service
public class ModelService {

    @Value("${male.model.default:qwen2.5:7b}")
    private String defaultModel;

    @Value("${male.model.fast:qwen3.5:9b}")
    private String fastModel;

    @Value("${male.model.primary:gemma4:12b-it-qat}")
    private String primaryModel;

    private final RestTemplate restTemplate;

    /**
     * Construtor do ModelService
     * Configura o RestTemplate com timeout de 5 segundos
     */
    public ModelService() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);
        factory.setReadTimeout(5000);
        this.restTemplate = new RestTemplate(factory);
    }

    /**
     * Resolve o modelo a ser usado, verificando se foi solicitado, se está na variável de ambiente ou se deve descobrir o melhor modelo disponível.
     * @param requested Modelo solicitado
     * @return Modelo a ser usado
     */
    public String resolveModel(String requested) {
        if (requested != null && !requested.isEmpty() && !"auto".equals(requested)) {
            return requested;
        }
        String envModel = System.getenv("OLLAMA_MODEL");
        if (envModel != null && !envModel.isEmpty()) {
            return envModel;
        }
        return discoverBestModel();
    }

    /**
     * Descobre o melhor modelo disponível na ordem de prioridade definida nas variáveis de ambiente
     */
    public String discoverBestModel() {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> response = restTemplate.getForObject(
                    "http://localhost:11434/api/tags", Map.class);
            if (response != null && response.containsKey("models")) {
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> models = (List<Map<String, Object>>) response.get("models");
                if (models != null) {
                    List<String> modelNames = models.stream()
                            .map(m -> (String) m.get("name"))
                            .toList();

                    if (modelNames.contains(fastModel))
                        return fastModel;
                    if (modelNames.contains(primaryModel))
                        return primaryModel;
                    if (modelNames.contains(defaultModel))
                        return defaultModel;
                    if (!modelNames.isEmpty())
                        return modelNames.get(0);
                }
            }
        } catch (Exception e) {
            // Ollama not available
        }
        return defaultModel;
    }

    /**
     * Retorna a lista de modelos disponíveis no Ollama
     * @return Lista de modelos disponíveis
     */
    public List<String> listAvailableModels() {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> response = restTemplate.getForObject(
                    "http://localhost:11434/api/tags", Map.class);
            if (response != null && response.containsKey("models")) {
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> models = (List<Map<String, Object>>) response.get("models");
                if (models != null) {
                    return models.stream()
                            .map(m -> (String) m.get("name"))
                            .toList();
                }
            }
        } catch (Exception e) {
            // Ollama not available
        }
        return List.of();
    }
}
