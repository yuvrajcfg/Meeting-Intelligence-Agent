IF OBJECT_ID(N'dbo.Meetings', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Meetings
    (
        MeetingId BIGINT IDENTITY(1,1) NOT NULL,
        Title NVARCHAR(200) NOT NULL,
        Transcript NVARCHAR(MAX) NOT NULL,
        MeetingDate DATETIMEOFFSET(7) NULL,
        IndexingTaskId UNIQUEIDENTIFIER NULL,
        IndexingStatus NVARCHAR(20) NOT NULL
            CONSTRAINT DF_Meetings_IndexingStatus DEFAULT N'not_indexed',
        IndexingError NVARCHAR(1000) NULL,
        FileName NVARCHAR(255) NULL,
        FileType NVARCHAR(20) NULL,
        FileSize BIGINT NULL,
        UploadedAt DATETIMEOFFSET(7) NULL,
        IndexedAt DATETIMEOFFSET(7) NULL,
        ChunkCount INT NULL,
        OriginalFilePath NVARCHAR(1000) NULL,
        CleanedTextPath NVARCHAR(1000) NULL,
        ChromaCollection NVARCHAR(100) NULL,
        CreatedAt DATETIMEOFFSET(7) NOT NULL
            CONSTRAINT DF_Meetings_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIMEOFFSET(7) NOT NULL
            CONSTRAINT DF_Meetings_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_Meetings PRIMARY KEY CLUSTERED (MeetingId),
        CONSTRAINT CK_Meetings_Title_NotEmpty CHECK (LEN(LTRIM(RTRIM(Title))) > 0),
        CONSTRAINT CK_Meetings_Transcript_NotEmpty CHECK (LEN(LTRIM(RTRIM(Transcript))) > 0),
        CONSTRAINT CK_Meetings_IndexingStatus CHECK
            (IndexingStatus IN (N'not_indexed', N'pending', N'processing', N'ready', N'failed'))
    );
END;
GO

IF COL_LENGTH(N'dbo.Meetings', N'FileName') IS NULL
    ALTER TABLE dbo.Meetings ADD FileName NVARCHAR(255) NULL;
IF COL_LENGTH(N'dbo.Meetings', N'FileType') IS NULL
    ALTER TABLE dbo.Meetings ADD FileType NVARCHAR(20) NULL;
IF COL_LENGTH(N'dbo.Meetings', N'FileSize') IS NULL
    ALTER TABLE dbo.Meetings ADD FileSize BIGINT NULL;
IF COL_LENGTH(N'dbo.Meetings', N'UploadedAt') IS NULL
    ALTER TABLE dbo.Meetings ADD UploadedAt DATETIMEOFFSET(7) NULL;
IF COL_LENGTH(N'dbo.Meetings', N'IndexedAt') IS NULL
    ALTER TABLE dbo.Meetings ADD IndexedAt DATETIMEOFFSET(7) NULL;
IF COL_LENGTH(N'dbo.Meetings', N'ChunkCount') IS NULL
    ALTER TABLE dbo.Meetings ADD ChunkCount INT NULL;
IF COL_LENGTH(N'dbo.Meetings', N'OriginalFilePath') IS NULL
    ALTER TABLE dbo.Meetings ADD OriginalFilePath NVARCHAR(1000) NULL;
IF COL_LENGTH(N'dbo.Meetings', N'CleanedTextPath') IS NULL
    ALTER TABLE dbo.Meetings ADD CleanedTextPath NVARCHAR(1000) NULL;
IF COL_LENGTH(N'dbo.Meetings', N'ChromaCollection') IS NULL
    ALTER TABLE dbo.Meetings ADD ChromaCollection NVARCHAR(100) NULL;
GO

IF OBJECT_ID(N'dbo.CK_Meetings_IndexingStatus', N'C') IS NOT NULL
    ALTER TABLE dbo.Meetings DROP CONSTRAINT CK_Meetings_IndexingStatus;
GO

UPDATE dbo.Meetings
SET IndexingStatus = CASE IndexingStatus
    WHEN N'queued' THEN N'pending'
    WHEN N'indexing' THEN N'processing'
    WHEN N'indexed' THEN N'ready'
    ELSE IndexingStatus
END;
GO

ALTER TABLE dbo.Meetings
    ADD CONSTRAINT CK_Meetings_IndexingStatus CHECK
        (IndexingStatus IN (N'not_indexed', N'pending', N'processing', N'ready', N'failed'));
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.Meetings')
      AND name = N'IX_Meetings_CreatedAt_MeetingId'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_Meetings_CreatedAt_MeetingId
        ON dbo.Meetings (CreatedAt DESC, MeetingId)
        INCLUDE (Title, MeetingDate);
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_Create
    @Title NVARCHAR(200),
    @Transcript NVARCHAR(MAX),
    @IndexingTaskId UNIQUEIDENTIFIER,
    @MeetingDate DATETIMEOFFSET(7) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Now DATETIMEOFFSET(7) = SYSUTCDATETIME();
    DECLARE @CreatedMeeting TABLE
    (
        MeetingId BIGINT,
        Title NVARCHAR(200),
        Transcript NVARCHAR(MAX),
        MeetingDate DATETIMEOFFSET(7),
        IndexingTaskId UNIQUEIDENTIFIER,
        IndexingStatus NVARCHAR(20),
        IndexingError NVARCHAR(1000),
        FileName NVARCHAR(255),
        FileType NVARCHAR(20),
        FileSize BIGINT,
        UploadedAt DATETIMEOFFSET(7),
        IndexedAt DATETIMEOFFSET(7),
        ChunkCount INT,
        OriginalFilePath NVARCHAR(1000),
        CleanedTextPath NVARCHAR(1000),
        ChromaCollection NVARCHAR(100),
        CreatedAt DATETIMEOFFSET(7),
        UpdatedAt DATETIMEOFFSET(7)
    );

    INSERT INTO dbo.Meetings
        (Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus, CreatedAt, UpdatedAt)
        OUTPUT inserted.MeetingId, inserted.Title, inserted.Transcript,
            inserted.MeetingDate, inserted.IndexingTaskId, inserted.IndexingStatus,
            inserted.IndexingError, inserted.FileName, inserted.FileType,
            inserted.FileSize, inserted.UploadedAt, inserted.IndexedAt,
            inserted.ChunkCount, inserted.OriginalFilePath, inserted.CleanedTextPath,
            inserted.ChromaCollection, inserted.CreatedAt, inserted.UpdatedAt
        INTO @CreatedMeeting
    VALUES (@Title, @Transcript, @MeetingDate, @IndexingTaskId, N'pending', @Now, @Now);

    SELECT MeetingId, Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus,
        IndexingError, FileName, FileType, FileSize, UploadedAt, IndexedAt, ChunkCount,
        OriginalFilePath, CleanedTextPath, ChromaCollection, CreatedAt, UpdatedAt
    FROM @CreatedMeeting;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_Count
    @Search NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT COUNT_BIG(*) AS TotalCount
    FROM dbo.Meetings
    WHERE @Search IS NULL
       OR CHARINDEX(@Search, Title) > 0
       OR CHARINDEX(@Search, Transcript) > 0;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_List
    @Search NVARCHAR(100) = NULL,
    @Offset INT = 0,
    @Limit INT = 20
AS
BEGIN
    SET NOCOUNT ON;

    SELECT MeetingId, Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus,
        IndexingError, FileName, FileType, FileSize, UploadedAt, IndexedAt, ChunkCount,
        OriginalFilePath, CleanedTextPath, ChromaCollection, CreatedAt, UpdatedAt
    FROM dbo.Meetings
    WHERE @Search IS NULL
       OR CHARINDEX(@Search, Title) > 0
       OR CHARINDEX(@Search, Transcript) > 0
    ORDER BY CreatedAt DESC, MeetingId
    OFFSET @Offset ROWS
    FETCH NEXT @Limit ROWS ONLY;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_ListIndexStatus
    @Offset INT = 0,
    @Limit INT = 20
AS
BEGIN
    SET NOCOUNT ON;

    SELECT MeetingId, Title, MeetingDate, IndexingTaskId, IndexingStatus, IndexingError
    FROM dbo.Meetings
    ORDER BY CreatedAt DESC, MeetingId
    OFFSET @Offset ROWS
    FETCH NEXT @Limit ROWS ONLY;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_Get
    @MeetingId BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT MeetingId, Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus,
        IndexingError, FileName, FileType, FileSize, UploadedAt, IndexedAt, ChunkCount,
        OriginalFilePath, CleanedTextPath, ChromaCollection, CreatedAt, UpdatedAt
    FROM dbo.Meetings
    WHERE MeetingId = @MeetingId;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_Update
    @MeetingId BIGINT,
    @Title NVARCHAR(200),
    @Transcript NVARCHAR(MAX),
    @IndexingTaskId UNIQUEIDENTIFIER,
    @MeetingDate DATETIMEOFFSET(7) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.Meetings
    SET Title = @Title,
        Transcript = @Transcript,
        MeetingDate = @MeetingDate,
        IndexingTaskId = @IndexingTaskId,
        IndexingStatus = N'pending',
        IndexingError = NULL,
        FileName = NULL,
        FileType = NULL,
        FileSize = NULL,
        UploadedAt = NULL,
        IndexedAt = NULL,
        ChunkCount = NULL,
        OriginalFilePath = NULL,
        CleanedTextPath = NULL,
        ChromaCollection = NULL,
        UpdatedAt = SYSUTCDATETIME()
    WHERE MeetingId = @MeetingId;

    SELECT MeetingId, Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus,
        IndexingError, FileName, FileType, FileSize, UploadedAt, IndexedAt, ChunkCount,
        OriginalFilePath, CleanedTextPath, ChromaCollection, CreatedAt, UpdatedAt
    FROM dbo.Meetings
    WHERE MeetingId = @MeetingId;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_QueueIndexing
    @MeetingId BIGINT,
    @IndexingTaskId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.Meetings
    SET IndexingTaskId = @IndexingTaskId,
        IndexingStatus = N'pending',
        IndexingError = NULL,
        IndexedAt = NULL,
        ChunkCount = NULL,
        UpdatedAt = SYSUTCDATETIME()
    WHERE MeetingId = @MeetingId;

    SELECT MeetingId, Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus,
        IndexingError, FileName, FileType, FileSize, UploadedAt, IndexedAt, ChunkCount,
        OriginalFilePath, CleanedTextPath, ChromaCollection, CreatedAt, UpdatedAt
    FROM dbo.Meetings
    WHERE MeetingId = @MeetingId;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_SetIndexingStatus
    @MeetingId BIGINT,
    @IndexingTaskId UNIQUEIDENTIFIER,
    @IndexingStatus NVARCHAR(20),
    @IndexingError NVARCHAR(1000) = NULL,
    @IndexedAt DATETIMEOFFSET(7) = NULL,
    @ChunkCount INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.Meetings
    SET IndexingStatus = @IndexingStatus,
        IndexingError = @IndexingError,
        IndexedAt = @IndexedAt,
        ChunkCount = @ChunkCount,
        UpdatedAt = SYSUTCDATETIME()
    WHERE MeetingId = @MeetingId
      AND IndexingTaskId = @IndexingTaskId;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_SetUploadMetadata
    @MeetingId BIGINT,
    @FileName NVARCHAR(255),
    @FileType NVARCHAR(20),
    @FileSize BIGINT,
    @UploadedAt DATETIMEOFFSET(7),
    @OriginalFilePath NVARCHAR(1000),
    @CleanedTextPath NVARCHAR(1000),
    @ChromaCollection NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.Meetings
    SET FileName = @FileName,
        FileType = @FileType,
        FileSize = @FileSize,
        UploadedAt = @UploadedAt,
        OriginalFilePath = @OriginalFilePath,
        CleanedTextPath = @CleanedTextPath,
        ChromaCollection = @ChromaCollection,
        UpdatedAt = SYSUTCDATETIME()
    WHERE MeetingId = @MeetingId;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_Delete
    @MeetingId BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM dbo.Meetings
        OUTPUT deleted.MeetingId, deleted.Title
    WHERE MeetingId = @MeetingId;
END;
GO
