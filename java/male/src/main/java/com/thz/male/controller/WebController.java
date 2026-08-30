package com.thz.male.controller;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

import com.thz.male.service.ModelService;

/**
 * Controller Web para debates
 * - index: lista modelos disponíveis e inicia debate
 */
@Controller
public class WebController {

    private final ModelService modelService;

    public WebController(ModelService modelService) {
        this.modelService = modelService;
    }

    @GetMapping("/")
    public String index(Model model) {
        model.addAttribute("availableModels", modelService.listAvailableModels());
        return "index";
    }
}
