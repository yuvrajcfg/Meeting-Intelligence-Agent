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
        CreatedAt DATETIMEOFFSET(7) NOT NULL
            CONSTRAINT DF_Meetings_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIMEOFFSET(7) NOT NULL
            CONSTRAINT DF_Meetings_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_Meetings PRIMARY KEY CLUSTERED (MeetingId),
        CONSTRAINT CK_Meetings_Title_NotEmpty CHECK (LEN(LTRIM(RTRIM(Title))) > 0),
        CONSTRAINT CK_Meetings_Transcript_NotEmpty CHECK (LEN(LTRIM(RTRIM(Transcript))) > 0),
        CONSTRAINT CK_Meetings_IndexingStatus CHECK
            (IndexingStatus IN (N'not_indexed', N'queued', N'indexing', N'indexed', N'failed'))
    );
END;
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
        CreatedAt DATETIMEOFFSET(7),
        UpdatedAt DATETIMEOFFSET(7)
    );

    INSERT INTO dbo.Meetings
        (Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus, CreatedAt, UpdatedAt)
        OUTPUT inserted.MeetingId, inserted.Title, inserted.Transcript,
            inserted.MeetingDate, inserted.IndexingTaskId, inserted.IndexingStatus,
            inserted.IndexingError, inserted.CreatedAt, inserted.UpdatedAt
        INTO @CreatedMeeting
    VALUES (@Title, @Transcript, @MeetingDate, @IndexingTaskId, N'queued', @Now, @Now);

    SELECT MeetingId, Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus,
        IndexingError, CreatedAt, UpdatedAt
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
        IndexingError, CreatedAt, UpdatedAt
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
        IndexingError, CreatedAt, UpdatedAt
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
    IndexingStatus = N'queued',
    IndexingError = NULL,
        UpdatedAt = SYSUTCDATETIME()
    WHERE MeetingId = @MeetingId;

    SELECT MeetingId, Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus,
        IndexingError, CreatedAt, UpdatedAt
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
        IndexingStatus = N'queued',
        IndexingError = NULL
    WHERE MeetingId = @MeetingId;

    SELECT MeetingId, Title, Transcript, MeetingDate, IndexingTaskId, IndexingStatus,
        IndexingError, CreatedAt, UpdatedAt
    FROM dbo.Meetings
    WHERE MeetingId = @MeetingId;
END;
GO

CREATE OR ALTER PROCEDURE dbo.Meeting_SetIndexingStatus
    @MeetingId BIGINT,
    @IndexingTaskId UNIQUEIDENTIFIER,
    @IndexingStatus NVARCHAR(20),
    @IndexingError NVARCHAR(1000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.Meetings
    SET IndexingStatus = @IndexingStatus,
        IndexingError = @IndexingError
    WHERE MeetingId = @MeetingId
      AND IndexingTaskId = @IndexingTaskId;
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
