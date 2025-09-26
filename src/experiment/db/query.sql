-- name: getDataset :many
select *
from dataset
order by id asc;

-- name: getIfcModels :many
select *
from ifc_models;

-- name: insertExperiment :one
INSERT INTO experiment
    (name, mlflow_id, type, timestamp)
VALUES
    (?, ?, ?, ?)
RETURNING *;

