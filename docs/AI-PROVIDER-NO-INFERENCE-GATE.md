# Limite do gate autenticado

O gate de conectividade Gemini desta etapa não executa geração de conteúdo. Ele consulta somente o catálogo de modelos do provedor para verificar autenticação e disponibilidade do modelo configurado.

Consequentemente, o gate não deve consumir prompts de negócio, anúncios, pedidos, métricas, mensagens, dados pessoais ou telemetria do Mercado Livre. Qualquer futura inferência externa exige uma etapa própria de minimização de dados e contrato explícito de uso.
