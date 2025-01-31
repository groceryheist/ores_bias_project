source("modeling_init.R", local=TRUE)
library(rstanarm)
#mcaffinity(1:detectCores()) ## required and explained below 
options(mc.cores = parallel::detectCores())
partial <- purrr::partial

## first lets fit the all pooling model.
## under reasonable assumptions this can identify the LATE of having a revision scored above a threshhold.


if(! exists("overwrite"))
    overwrite <- TRUE

source("rdd_defaults.R")
if(!exists("sample.filename")){
    print('using default sample')
    sample.filename<-"cutoff_revisions_sample.csv"
}

if(!exists("strata.counts.filename")){
    print('using default weights')
    strata.counts.filename <- "threshold_strata_counts_sample.csv"
}

df  <- build.rdd.dbds(filename <- sample.filename,
                      strata_counts <- strata.counts.filename)

revert.df <- df[reverted.in.48h == TRUE]
#we moved to a bigger dataset so increase p
remember(p,'bandwidth')

min.obs.per.wiki.threshold <- 3
df <- df[,within.neighborhood := d.abs.nearest.threshold <= p]
df <- df[(within.neighborhood==T)]
#df <- df[wiki.db %in% c('eswiki','frwiki','fiwiki','enwiki')]
remember(min.obs.per.wiki.threshold, 'min.obs.per.wiki.threshold.cutoff')

check.adoption <- function(wiki){

    model.path <- file.path("models",paste0("adoption.check.",wiki,'.stanmod.RDS'))
    if(!file.exists(model.path)){
        return(FALSE)
    }
    model <- readRDS(model.path)
    draws <- as.data.table(model$stanfit)
    var1 <- "nearest.thresholdmaybebad:gt.nearest.thresholdTRUE"
    var2 <- "nearest.thresholdlikelybad:gt.nearest.thresholdTRUE"
    var3 <- "nearest.thresholdverylikelybad:gt.nearest.thresholdTRUE"

    var.is.significant <- function(var, draws, level=0.95){
        draws <- draws[[var]]
        q <- quantile(draws,probs = c( (1 - level)/2, level + (1 - level)/2))
        if( (q[1] > 0) && (q[2] > 0)){
            return(TRUE)
        } else {
            return(FALSE)
        }
    }

    return(any(sapply(c(var1, var2, var3), function(var) var.is.significant(var, draws, 0.95))))
}


prepare.model  <- function(dta, name, form, do.remember=TRUE, drop.verylikelybad=FALSE){

    if(drop.verylikelybad==TRUE){
        n.thresholds <- 2
        dta <- dta[nearest.threshold != 'verylikelybad']
    } else {        
        n.thresholds <- length(unique(dta$nearest.threshold))
    }

    outcome <- all.vars(form)[1] 
    dta <- dta[!is.na(nearest.threshold)]
    # don't include nas in calculating weights
    dta <- dta[!is.na(dta[[outcome]])]
    obs.per.wiki.threshold <- dta[,.(.N),by=.(wiki.db, nearest.threshold)]
    obs.per.wiki.threshold <- obs.per.wiki.threshold[N >= min.obs.per.wiki.threshold]
    thresholds.per.wiki <- obs.per.wiki.threshold[,.(.N), by=.(wiki.db)]

    included.wikis <- thresholds.per.wiki[N==n.thresholds]$wiki.db
    excluded.wikis <- thresholds.per.wiki[N!=n.thresholds]$wiki.db
## excluded.wikis <- c()
##     ## drop wikis with less than 100 observations
##     for(wiki in unique(dta$wiki.db)){
##         for(threshold in unique(dta$nearest.threshold)){
##             n.obs.below <- nrow(dta[ (wiki.db == wiki) &
##                                      (nearest.threshold == threshold) &


##             n.obs.above  <- nrow(dta[ (wiki.db == wiki) &
##                                      (nearest.threshold == threshold) &
##                                      (gt.nearest.threshold == TRUE)])
##             if( (n.obs.below < min.obs.per.wiki.threshold) &
##                 (n.obs.above < min.obs.per.wiki.threshold)){
##                 excluded.wikis <- c(excluded.wikis, wiki)
##             }
##         }
##     }p

    if(do.remember == TRUE){
        remember(excluded.wikis,
                 paste(name,'excluded.wikis',sep='.'))

        remember(included.wikis,
                 paste(name,'included.wikis',sep='.'))

    }

    dta  <- dta[wiki.db %in% included.wikis]

    if(do.remember == TRUE)
        remember(dta[,.(N=.N,total.weight=sum(weight)),by=.(wiki.db,nearest.threshold)], paste(name,'samplesize.bywikithresh',sep='.'))

    #rescale weight so it sums to N
    strata <- unique(dta[,.(strata, count, obs.count=.N),by=.(strata)])
    dta <- dta[,c("count","fraction"):=NULL]
    multi.threshold <- FALSE
    if(length(unique(strata$nearest.threshold)) > 1){
        strata <- strata[, N := sum(count),by=.(nearest.threshold)]
        multi.threshold <- TRUE
    } else {
        strata <- strata[, N := sum(count)]
    }
    # fraction is the probability an observation 
    strata <- strata[,pop.fraction:= count/N]
    dta <- dta[strata, on=.(strata)]

    if(multi.threshold){
        total.obs <- dta[,.(N),by=.(nearest.threshold)]
    } else {
        total.obs <- nrow(dta)
    }
    ## weights should be (prop of population in strata) / (fraction of observations in strata)
    
    dta <- dta[, obs.fraction := .N/total.obs, by=.(strata)]
    dta <- dta[, weight := pop.fraction/obs.fraction]

    return(dta)
} 

fit.model  <- function(dta, name, form, do.remember=TRUE, drop.verylikelybad = FALSE){
#    mcaffinity(1:detectCores()) ## required and explained below 
    options(mc.cores = parallel::detectCores())

    dta  <- prepare.model(dta,name,form, do.remember, drop.verylikelybad = drop.verylikelybad)
    dta  <- data.frame(dta)

    assign("dta",dta,envir=globalenv())

    mod <- stan_glm(formula=form,
                    family=binomial(link='logit'),
                    chains=chains,
                    data=dta,
                    weights=dta[['weight']],
                    iter=iter,
                    warmup=warmup,
                    refresh=refresh,
                    QR=QR
                    )

    saveRDS(mod, file.path("/gscratch/comdata/users/nathante/ores_bias_project/sample_models", paste(name,"stanmod","RDS", sep='.')))
    return(mod)
} 

