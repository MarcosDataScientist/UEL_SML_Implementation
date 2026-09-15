-- ==============================================================================
-- Esquema e Carga de Testes: Orçamento Público do Paraná (SEFA / UEL)
-- Extensões: pg_trgm (fuzzy search / similaridade) e unaccent (remoção de acentos)
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ------------------------------------------------------------------------------
-- 1. Ações Orçamentárias (acaoorcamentaria)
-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS acaoorcamentaria CASCADE;
CREATE TABLE acaoorcamentaria (
    id SERIAL PRIMARY KEY,
    codigoacaoorcamentaria INT NOT NULL,
    nomeacao VARCHAR(255) NOT NULL,
    esfera VARCHAR(50) DEFAULT 'Estadual',
    programa VARCHAR(100) DEFAULT 'Gestão Pública e Desenvolvimento'
);

CREATE INDEX idx_acaoorcamentaria_codigo ON acaoorcamentaria(codigoacaoorcamentaria);
CREATE INDEX idx_acaoorcamentaria_nome_trgm ON acaoorcamentaria USING gin (unaccent(lower(nomeacao)) gin_trgm_ops);

INSERT INTO acaoorcamentaria (codigoacaoorcamentaria, nomeacao, esfera, programa) VALUES
(8000, 'Encargos Gerais do Estado - Operações Especiais', 'Estadual', 'Operações Especiais'),
(8050, 'Encargos Previdenciários da Administração Pública', 'Estadual', 'Previdência'),
(5050, 'Manutenção e Modernização da Universidade Estadual de Londrina - UEL', 'Estadual', 'Educação Superior'),
(5051, 'Ações de Extensão Universitária e Apoio à Comunidade - UEL', 'Estadual', 'Educação Superior'),
(5052, 'Pesquisa Científica e Inovação Tecnológica na UEL', 'Estadual', 'Ciência e Tecnologia'),
(4010, 'Atenção Primária e Vigilância em Saúde no Estado', 'Estadual', 'Saúde Pública'),
(4020, 'Atendimento Ambulatorial e Hospitalar de Média e Alta Complexidade', 'Estadual', 'Saúde Pública'),
(2040, 'Conservação e Reforma de Prédios Públicos e Instalações', 'Estadual', 'Infraestrutura e Obras'),
(2045, 'Serviços de Manutenção Predial e Limpeza de Campus Universitário', 'Estadual', 'Infraestrutura e Obras'),
(6010, 'Apoio ao Desenvolvimento Científico e Tecnológico - Fundação Araucária', 'Estadual', 'Ciência e Tecnologia');

-- ------------------------------------------------------------------------------
-- 2. Natureza da Despesa e Subelemento Detalhe
-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS naturezadespesa CASCADE;
CREATE TABLE naturezadespesa (
    id SERIAL PRIMARY KEY,
    naturezadespesaformatada VARCHAR(20) NOT NULL,
    descricaosubelemento VARCHAR(255) NOT NULL
);

CREATE INDEX idx_natureza_formatada ON naturezadespesa(naturezadespesaformatada);
CREATE INDEX idx_natureza_desc_trgm ON naturezadespesa USING gin (unaccent(lower(descricaosubelemento)) gin_trgm_ops);

INSERT INTO naturezadespesa (naturezadespesaformatada, descricaosubelemento) VALUES
('3.3.90.30.00', 'Material de Consumo'),
('3.3.90.39.00', 'Outros Serviços de Terceiros - Pessoa Jurídica'),
('3.3.90.36.00', 'Outros Serviços de Terceiros - Pessoa Física'),
('4.4.90.52.00', 'Equipamentos e Material Permanente'),
('3.3.90.14.00', 'Diárias - Civil'),
('3.3.90.40.00', 'Serviços de Tecnologia da Informação e Comunicação - PJ');

DROP TABLE IF EXISTS subelementodetalhe CASCADE;
CREATE TABLE subelementodetalhe (
    id SERIAL PRIMARY KEY,
    naturezadespesa VARCHAR(20) NOT NULL,
    descricaosubelementodetalhe VARCHAR(255) NOT NULL,
    titulosubelementodetalhe VARCHAR(255) NOT NULL
);

INSERT INTO subelementodetalhe (naturezadespesa, descricaosubelementodetalhe, titulosubelementodetalhe) VALUES
('3.3.90.30.00', 'Material de Limpeza e Higienização Predial', 'Material de Limpeza'),
('3.3.90.30.00', 'Combustíveis e Lubrificantes Automotivos', 'Combustíveis'),
('3.3.90.30.00', 'Material de Expediente e Escritório', 'Material de Escritório'),
('3.3.90.39.00', 'Serviços de Manutenção e Reforma de Telhados e Alvenaria', 'Reforma e Conservação Predial'),
('3.3.90.39.00', 'Serviço de Limpeza, Asseio e Conservação Predial Contratada', 'Limpeza Predial Terceirizada'),
('3.3.90.39.00', 'Serviços Técnicos e Científicos de Consultoria e Auditoria', 'Consultoria e Perícia'),
('4.4.90.52.00', 'Aparelhos e Utensílios de Informática e Computadores', 'Hardware e Servidores'),
('4.4.90.52.00', 'Mobiliário em Geral e Móveis para Escritório', 'Mobiliário em Geral');

-- ------------------------------------------------------------------------------
-- 3. Funções e Subfunções
-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS funcao CASCADE;
CREATE TABLE funcao (
    idfuncao SERIAL PRIMARY KEY,
    codigofuncao INT NOT NULL,
    descricaofuncao VARCHAR(100) NOT NULL
);

INSERT INTO funcao (codigofuncao, descricaofuncao) VALUES
(4, 'Administração'),
(10, 'Saúde'),
(12, 'Educação'),
(19, 'Ciência e Tecnologia'),
(28, 'Encargos Especiais');

DROP TABLE IF EXISTS subfuncao CASCADE;
CREATE TABLE subfuncao (
    idsubfuncao SERIAL PRIMARY KEY,
    codigosubfuncao INT NOT NULL,
    descricaosubfuncao VARCHAR(150) NOT NULL,
    funcao_idfuncao INT REFERENCES funcao(idfuncao)
);

CREATE INDEX idx_subfuncao_cod ON subfuncao(codigosubfuncao);
CREATE INDEX idx_subfuncao_desc_trgm ON subfuncao USING gin (unaccent(lower(descricaosubfuncao)) gin_trgm_ops);

INSERT INTO subfuncao (codigosubfuncao, descricaosubfuncao, funcao_idfuncao) VALUES
(122, 'Administração Geral', 1),
(302, 'Assistência Hospitalar e Ambulatorial', 2),
(301, 'Atenção Básica em Saúde', 2),
(364, 'Ensino Superior', 3),
(368, 'Educação Básica e Profissional', 3),
(571, 'Desenvolvimento Científico', 4),
(846, 'Outros Encargos Especiais', 5);

-- ------------------------------------------------------------------------------
-- 4. Fontes de Recursos (fonte, grupofonte, exercicio)
-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS grupofonte CASCADE;
CREATE TABLE grupofonte (
    idgrupofonte SERIAL PRIMARY KEY,
    codigogrupofonte INT NOT NULL,
    nomegrupofonte VARCHAR(150) NOT NULL
);

INSERT INTO grupofonte (codigogrupofonte, nomegrupofonte) VALUES
(1, 'Recursos do Tesouro - Exercício Corrente'),
(2, 'Recursos de Outras Fontes - Exercício Corrente'),
(3, 'Recursos Próprios das Entidades Indiretas');

DROP TABLE IF EXISTS exercicio CASCADE;
CREATE TABLE exercicio (
    idexercicio SERIAL PRIMARY KEY,
    codigoexercicio INT NOT NULL,
    nomeexercicio VARCHAR(50) NOT NULL,
    ativo INT DEFAULT 1,
    excluido INT DEFAULT 0
);

INSERT INTO exercicio (codigoexercicio, nomeexercicio, ativo, excluido) VALUES
(2026, 'Exercício Financeiro 2026', 1, 0),
(2025, 'Exercício Financeiro 2025', 0, 0);

DROP TABLE IF EXISTS fonte CASCADE;
CREATE TABLE fonte (
    idfonte SERIAL PRIMARY KEY,
    codigofonte INT NOT NULL,
    fonte VARCHAR(255) NOT NULL,
    marcadorfonte VARCHAR(50),
    tipodetfonte VARCHAR(50),
    titulofonte VARCHAR(255),
    pertencetesouro INT DEFAULT 1,
    exerciciofonte INT DEFAULT 2026,
    detalhamentofonte TEXT,
    detalhamentofontemto TEXT,
    detalhamentofontesiafic VARCHAR(50),
    grupofonte_idgrupofonte INT REFERENCES grupofonte(idgrupofonte),
    exercicio_idexercicio INT REFERENCES exercicio(idexercicio),
    ativo INT DEFAULT 1,
    excluido INT DEFAULT 0
);

CREATE INDEX idx_fonte_codigo ON fonte(codigofonte);
CREATE INDEX idx_fonte_siafic ON fonte(detalhamentofontesiafic);
CREATE INDEX idx_fonte_titulo_trgm ON fonte USING gin (unaccent(lower(COALESCE(titulofonte, ''))) gin_trgm_ops);

INSERT INTO fonte (
    codigofonte, fonte, marcadorfonte, tipodetfonte, titulofonte, pertencetesouro,
    exerciciofonte, detalhamentofonte, detalhamentofontemto, detalhamentofontesiafic,
    grupofonte_idgrupofonte, exercicio_idexercicio, ativo, excluido
) VALUES
(100, 'Recursos Ordinários Livres do Tesouro Estadual', 'LIVRE', 'Tesouro', 'Recursos Livres do Tesouro', 1, 2026, 'Recursos arrecadados livremente pelo Tesouro do Estado do Paraná', 'Fonte 100 MTO Geral', '100', 1, 1, 1, 0),
(101, 'Receitas de Impostos e Transferências Constitucionais - Educação', 'VINC_EDUC', 'Vinculada', 'Manutenção e Desenvolvimento do Ensino - MDE', 1, 2026, 'Vinculação constitucional de 25% para a educação estadual', 'Fonte 101 MDE', '101', 1, 1, 1, 0),
(102, 'Receitas de Impostos - Ações e Serviços Públicos de Saúde', 'VINC_SAUDE', 'Vinculada', 'Ações e Serviços Públicos de Saúde - ASPS', 1, 2026, 'Vinculação constitucional de 12% para a saúde estadual', 'Fonte 102 ASPS', '102', 1, 1, 1, 0),
(250, 'Receitas Próprias da Universidade Estadual de Londrina', 'PROPRIO_UEL', 'Própria', 'Taxas, Emolumentos e Convênios de Pesquisa da UEL', 0, 2026, 'Recursos arrecadados diretamente pelo campus e convênios UEL', 'Fonte 250 UEL', '250', 3, 1, 1, 0);

-- ------------------------------------------------------------------------------
-- 5. Modalidade, Solicitação e DAD (Documento de Adequação Orçamentária)
-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS modalidade CASCADE;
CREATE TABLE modalidade (
    idmodalidade SERIAL PRIMARY KEY,
    nomemodalidade VARCHAR(100) NOT NULL
);

INSERT INTO modalidade (nomemodalidade) VALUES
('Suplementação por Anulação de Dotação'),
('Abertura de Crédito Especial'),
('Remanejamento Interno de Fontes');

DROP TABLE IF EXISTS solicitacao CASCADE;
CREATE TABLE solicitacao (
    idsolicitacao SERIAL PRIMARY KEY,
    titulosolicitacao VARCHAR(255) NOT NULL,
    descricao_modalidade VARCHAR(255),
    historico TEXT,
    justificativa_odc TEXT,
    justificativa_historico TEXT,
    modalidade_idmodalidade INT REFERENCES modalidade(idmodalidade)
);

DROP TABLE IF EXISTS limitecredito CASCADE;
CREATE TABLE limitecredito (
    id SERIAL PRIMARY KEY,
    solicitacao_idsolicitacao INT REFERENCES solicitacao(idsolicitacao),
    textoparadad TEXT
);

DROP TABLE IF EXISTS dad CASCADE;
CREATE TABLE dad (
    id SERIAL PRIMARY KEY,
    solicitacao_idsolicitacao INT REFERENCES solicitacao(idsolicitacao),
    dadesgotamentoalternativas TEXT,
    dadjustificativa TEXT,
    dadresponsabilizacao TEXT
);

INSERT INTO solicitacao (idsolicitacao, titulosolicitacao, descricao_modalidade, historico, justificativa_odc, justificativa_historico, modalidade_idmodalidade) VALUES
(101, 'Suplementação para Reforma de Telhado do Bloco Central UEL', 'Suplementação por Anulação de Dotação', 'Necessidade de intervenção urgente na cobertura do Bloco Central da UEL', 'Evitar goteiras que ameaçam laboratórios de pesquisa de inteligência artificial', 'Histórico de chuvas e laudo da prefeitura do campus da UEL', 1),
(102, 'Aquisição de Servidor para Inferência de SLM Local', 'Remanejamento Interno de Fontes', 'Adequação orçamentária do projeto de extensão universitária', 'Impossibilidade de contratação de APIs comerciais devido a sigilo de dados', 'Recursos da Fonte 250 remanejados para modernização de TI', 3);

INSERT INTO limitecredito (solicitacao_idsolicitacao, textoparadad) VALUES
(101, 'Existe saldo suficiente na dotação de origem sem prejuízo das atividades essenciais.'),
(102, 'Limite de crédito alinhado às diretrizes da SEFA-PR para despesas de capital.');

INSERT INTO dad (solicitacao_idsolicitacao, dadesgotamentoalternativas, dadjustificativa, dadresponsabilizacao) VALUES
(101, 'Foram avaliadas opções de reparo emergencial pontual, sendo necessária a reforma completa.', 'Risco iminente de perda de patrimônio público.', 'Ordenador de despesas da UEL.'),
(102, 'Não há disponibilidade de servidores GPU de alto custo; a solução SLM em CPU é a mais viável.', 'Adoção de modelos locais de inteligência artificial soberana.', 'Coordenadoria de TI e Gestão Orçamentária.');

-- ==============================================================================
-- Verificação de Sanidade das Cargas
-- ==============================================================================
SELECT 'acaoorcamentaria' AS tabela, COUNT(*) AS registros FROM acaoorcamentaria
UNION ALL
SELECT 'naturezadespesa', COUNT(*) FROM naturezadespesa
UNION ALL
SELECT 'subelementodetalhe', COUNT(*) FROM subelementodetalhe
UNION ALL
SELECT 'funcao', COUNT(*) FROM funcao
UNION ALL
SELECT 'subfuncao', COUNT(*) FROM subfuncao
UNION ALL
SELECT 'fonte', COUNT(*) FROM fonte
UNION ALL
SELECT 'solicitacao', COUNT(*) FROM solicitacao;
