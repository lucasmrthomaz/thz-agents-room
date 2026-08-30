package com.thz.male;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MaleApplication {

    public static void main(String[] args) {
        try {
            SpringApplication.run(MaleApplication.class, args);
        } catch (Exception e) {
            System.out.println("Erro ao iniciar aplicação: " + e.getMessage());
            e.printStackTrace();
        }
    }
}